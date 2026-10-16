"""Prompts for writing skills and predicates, and parsing the answers.

The core supplies the rules and the format; the plugin supplies the API description and the game
guide (from its handshake), so no game knowledge lives here.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from agent_core.library import NAME_PATTERN, RESERVED_NAMES, Skill
from agent_core.plugins import JsonObject, JsonValue

MAX_LIST_ITEMS = 25
MAX_LIBRARY_CODE = 1_500
MAX_FEEDBACK_LOGS = 20


class DraftError(ValueError):
    """The model's answer does not have the required format."""


@dataclass(frozen=True, slots=True)
class SkillDraft:
    name: str
    description: str
    code: str


@dataclass(frozen=True, slots=True)
class Feedback:
    """What the previous attempt did, for the next prompt."""

    attempt: int
    code: str
    problem: str
    logs: Sequence[str] = ()
    observation_after: JsonObject | None = None


def compact(value: JsonValue, max_items: int = MAX_LIST_ITEMS) -> JsonValue:
    """Shortens long lists (keeping the first items) so an observation fits a prompt."""
    if isinstance(value, list):
        items = [compact(item, max_items) for item in value[:max_items]]
        if len(value) > max_items:
            items.append(f"... {len(value) - max_items} more")
        return items
    if isinstance(value, dict):
        return {key: compact(item, max_items) for key, item in value.items()}
    return value


def _json(value: JsonValue) -> str:
    return json.dumps(compact(value), separators=(",", ":"))


def skill_system_prompt(skill_api: Sequence[JsonObject], guide: str) -> str:
    api = "\n".join(
        f"- {entry.get('name')} -> {entry.get('returns')}: {entry.get('description')}"
        for entry in skill_api
    )
    return f"""You write skills for a game-playing agent.

A skill is the BODY of an async JavaScript function. In scope are only `bot` (the API below),
`args` (an object of inputs) and `log(...values)`. Nothing else exists: no require, import,
process, timers, fetch or files.

Rules:
- Use only the API. Await every call. Each call can throw an Error with a reason; catch it only
  when you can recover, otherwise let it fail.
- Read positions and block kinds from `bot.observe()`; never hard-code coordinates.
- Check what calls return. When the goal cannot be reached, `throw new Error("reason")` so the
  failure is reported. Do not pretend success.
- Every loop needs a fixed upper bound. No endless waiting.
- Library skills listed in the task are defined for you: call them as `await name(args)`, do not
  redefine them. Prefer calling a library skill to repeating its steps.
- Write a general, reusable skill (it will be stored and reused in other worlds): a clear camelCase
  name, a one-sentence description, and inputs read from `args` with sensible defaults.
- Return a small JSON-serializable summary.

API:
{api}

Game guide:
{guide.strip()}

Answer in exactly this format and nothing else:
<name>camelCaseName</name>
<description>One sentence: what the skill does, its inputs, its result.</description>
<code>
...the function body...
</code>"""


def skill_user_prompt(
    goal: str,
    predicate: JsonValue,
    observation: JsonObject,
    library: Sequence[Skill],
    feedback: Sequence[Feedback],
) -> str:
    parts = [
        f"Task: {goal}",
        "After your skill returns, success is checked by this predicate on the observation "
        f"(three-valued; only true counts):\n{_json(predicate)}",
        f"Current observation:\n{_json(observation)}",
    ]
    if library:
        listed = "\n\n".join(
            f"- {skill.name}: {skill.description}\n```js\n{skill.code[:MAX_LIBRARY_CODE]}\n```"
            for skill in library
        )
        parts.append(f"Library skills you can call (await name(args)):\n{listed}")
    else:
        parts.append("The skill library is empty.")
    for item in feedback:
        logs = "\n".join(item.logs[-MAX_FEEDBACK_LOGS:]) or "(none)"
        after = (
            "(not available)" if item.observation_after is None else _json(item.observation_after)
        )
        parts.append(
            f"Attempt {item.attempt} failed: {item.problem}\n"
            f"Its code:\n```js\n{item.code}\n```\nIts logs:\n{logs}\n"
            f"Observation afterwards:\n{after}\n"
            "Fix the cause; do not repeat the same approach if it cannot work."
        )
    return "\n\n".join(parts)


_TAG = r"<{0}>\s*(.*?)\s*</{0}>"


def parse_skill(text: str) -> SkillDraft:
    found: dict[str, str] = {}
    for tag in ("name", "description", "code"):
        match = re.search(_TAG.format(tag), text, re.DOTALL)
        if match is None:
            raise DraftError(f"the answer has no <{tag}>…</{tag}> section")
        found[tag] = match.group(1).strip()
    code = re.sub(r"^```[a-zA-Z]*\n|\n?```$", "", found["code"]).strip()
    name = found["name"]
    if not NAME_PATTERN.fullmatch(name) or name in RESERVED_NAMES:
        raise DraftError(f"name {name!r} is not a camelCase identifier of 3 to 48 characters")
    if not code:
        raise DraftError("the code section is empty")
    if not found["description"]:
        raise DraftError("the description is empty")
    return SkillDraft(name, found["description"], code)


PREDICATE_LANGUAGE = """Predicates are JSON:
- {"type": "has_item", "item": NAME, "count": N}  (N >= 1, summed over inventory stacks)
- {"type": "near", "x": X, "y": Y, "z": Z, "radius": R, "dimension"?: NAME}
- {"type": "compare", "path": "dotted.path.in.observation", "op": "==|!=|<|<=|>|>=", "value": V}
- {"type": "all"|"any", "of": [predicates]} and {"type": "not", "of": predicate}
They are evaluated on the observation and give true, false or unknown; only true is success."""


def predicate_prompt(goal: str, observation: JsonObject) -> str:
    return f"""Write the acceptance test for a task before anyone tries it.

Task: {goal}

{PREDICATE_LANGUAGE}

Current observation (the test must be FALSE now, and become true only when the task is done):
{_json(observation)}

Answer with the predicate JSON only, inside <predicate>...</predicate>."""


def parse_predicate_answer(text: str) -> JsonValue:
    match = re.search(_TAG.format("predicate"), text, re.DOTALL)
    if match is None:
        raise DraftError("the answer has no <predicate>…</predicate> section")
    body = re.sub(r"^```[a-zA-Z]*\n|\n?```$", "", match.group(1).strip()).strip()
    try:
        value: JsonValue = json.loads(body)
    except json.JSONDecodeError as error:
        raise DraftError(f"the predicate is not valid JSON ({error})") from error
    return value
