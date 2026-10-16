"""The Voyager loop with a fake game and a scripted LLM: no server, no API key."""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agent_core.library import SkillLibrary
from agent_core.llm import BackendResult, LlmClient, LlmRequest, Usage
from agent_core.plugins import JsonObject
from agent_core.skills import SkillResult
from agent_core.telemetry import TelemetryRecorder
from agent_core.verifier import Verdict, parse_predicate
from agent_core.voyager import loop as loop_module
from agent_core.voyager.loop import VoyagerAgent
from agent_core.voyager.prompts import parse_skill
from agent_core.voyager.task import Task, TaskError, load_task

HAS_PICKAXE: JsonObject = {"type": "has_item", "item": "pickaxe"}


@pytest.fixture(autouse=True)
def quick_verdicts(monkeypatch: pytest.MonkeyPatch) -> None:
    # A failed attempt waits for the predicate; in a fake game nothing will change.
    monkeypatch.setattr(loop_module, "VERDICT_WAIT_S", 0.1)


def answer(name: str, code: str) -> str:
    return f"<name>{name}</name>\n<description>Does {name}.</description>\n<code>\n{code}\n</code>"


@dataclass
class ScriptedLlm:
    """Returns the scripted answers in order and keeps every request."""

    answers: list[str]
    provider: str = "scripted"
    requests: list[LlmRequest] = field(default_factory=list[LlmRequest])

    async def create(self, request: LlmRequest) -> BackendResult:
        self.requests.append(request)
        return BackendResult(
            text=self.answers.pop(0),
            served_model=request.model,
            stop_reason="end_turn",
            usage=Usage(input_tokens=100, output_tokens=50),
        )

    def prompt(self, index: int) -> str:
        return self.requests[index].messages[-1].content


@dataclass
class FakeGame:
    """Inventory changes when a skill containing `GIVE <item>` runs; anything else fails."""

    inventory: list[JsonObject] = field(default_factory=list[JsonObject])
    codes: list[str] = field(default_factory=list[str])

    async def observe(self) -> JsonObject:
        return {"inventory": list(self.inventory)}

    async def run_skill(self, code: str, timeout_s: float) -> SkillResult:
        self.codes.append(code)
        if "THROW" in code:
            return SkillResult("r", "error", None, "Error: no logs nearby", 5.0, 1, ("looked",))
        for line in code.splitlines():
            if line.strip().startswith("GIVE "):
                self.inventory.append({"name": line.split()[1], "count": 1})
        return SkillResult("r", "ok", {"done": True}, None, 5.0, 2, ())


def make_agent(
    tmp_path: Path, answers: list[str], *, learn: bool = True
) -> tuple[VoyagerAgent, ScriptedLlm]:
    backend = ScriptedLlm(answers)
    llm = LlmClient(backend, TelemetryRecorder(tmp_path / "t.jsonl"))
    library = SkillLibrary(tmp_path / "skills.sqlite")
    api: list[JsonObject] = [
        {"name": "bot.observe()", "returns": "observation", "description": "state"}
    ]
    agent = VoyagerAgent(llm, library, api, "Game guide text.", learn=learn)
    return agent, backend


def task(predicate: JsonObject | None = HAS_PICKAXE) -> Task:
    return Task(
        "make-pickaxe",
        "Make a pickaxe.",
        None if predicate is None else parse_predicate(predicate),
        predicate_spec=predicate,
    )


def test_success_on_the_first_attempt_stores_the_skill(tmp_path: Path) -> None:
    agent, llm = make_agent(tmp_path, [answer("makePickaxe", "GIVE pickaxe")])
    outcome = asyncio.run(agent.solve(task(), FakeGame(), trace_id="t"))
    assert outcome.verdict is Verdict.TRUE
    assert outcome.learned_skill == "makePickaxe"
    assert agent.library.get("makePickaxe") is not None
    prompt = llm.prompt(0)
    assert "Task: Make a pickaxe." in prompt
    assert '"item":"pickaxe"' in prompt
    assert "Game guide text." in llm.requests[0].system


def test_a_failure_is_fed_back_and_the_retry_succeeds(tmp_path: Path) -> None:
    agent, llm = make_agent(
        tmp_path, [answer("makePickaxe", "THROW"), answer("makePickaxe", "GIVE pickaxe")]
    )
    outcome = asyncio.run(agent.solve(task(), FakeGame(), trace_id="t"))
    assert outcome.verdict is Verdict.TRUE
    assert [a.status for a in outcome.attempts] == ["error", "ok"]
    retry = llm.prompt(1)
    assert "Attempt 1 failed" in retry
    assert "no logs nearby" in retry
    assert "THROW" in retry  # the failed code is shown


def test_a_skill_that_says_ok_but_misses_the_goal_is_not_success(tmp_path: Path) -> None:
    agent, _ = make_agent(tmp_path, [answer("makePickaxe", "GIVE stick")] * 3)
    outcome = asyncio.run(agent.solve(task(), FakeGame(), trace_id="t"))
    assert outcome.verdict is Verdict.FALSE
    assert outcome.reason == "out of attempts"
    assert len(outcome.attempts) == 3
    assert agent.library.all() == []


def test_a_malformed_answer_counts_as_an_attempt(tmp_path: Path) -> None:
    agent, llm = make_agent(
        tmp_path, ["here is some code: GIVE pickaxe", answer("makePickaxe", "GIVE pickaxe")]
    )
    outcome = asyncio.run(agent.solve(task(), FakeGame(), trace_id="t"))
    assert [a.status for a in outcome.attempts] == ["draft-error", "ok"]
    assert "could not be used" in llm.prompt(1)


def test_library_skills_are_offered_and_assembled_before_the_new_code(tmp_path: Path) -> None:
    agent, llm = make_agent(
        tmp_path, [answer("makeStonePickaxe", "await makePickaxe();\nGIVE stone_pickaxe")]
    )
    agent.library.add("makePickaxe", "Make a pickaxe from nothing.", "GIVE pickaxe", "earlier")
    game = FakeGame()
    stone = Task(
        "stone",
        "Make a stone pickaxe.",
        parse_predicate({"type": "has_item", "item": "stone_pickaxe"}),
    )
    outcome = asyncio.run(agent.solve(stone, game, trace_id="t"))
    assert outcome.verdict is Verdict.TRUE
    assert outcome.used_skills == ("makePickaxe",)
    assert "makePickaxe: Make a pickaxe from nothing." in llm.prompt(0)
    assert game.codes[0].startswith("// library skill: makePickaxe")
    assert "async function makePickaxe(args = {})" in game.codes[0]
    used = agent.library.get("makePickaxe")
    assert used is not None and used.uses == 1


def test_a_goal_that_already_holds_is_not_attempted(tmp_path: Path) -> None:
    agent, llm = make_agent(tmp_path, [])
    game = FakeGame(inventory=[{"name": "pickaxe", "count": 1}])
    outcome = asyncio.run(agent.solve(task(), game, trace_id="t"))
    assert outcome.verdict is Verdict.UNKNOWN
    assert outcome.reason == "predicate is true before any attempt"
    assert llm.requests == []


def test_without_a_predicate_the_llm_writes_one_and_it_must_be_false_now(
    tmp_path: Path,
) -> None:
    # True on the empty start inventory: it could never show that a skill did anything.
    already_true = (
        '<predicate>{"type": "not", "of": {"type": "has_item", "item": "pickaxe"}}</predicate>'
    )
    agent, llm = make_agent(
        tmp_path,
        [
            already_true,
            '<predicate>{"type": "has_item", "item": "pickaxe"}</predicate>',
            answer("makePickaxe", "GIVE pickaxe"),
        ],
    )
    outcome = asyncio.run(agent.solve(task(None), FakeGame(), trace_id="t"))
    assert outcome.verdict is Verdict.TRUE
    assert outcome.predicate == {"type": "has_item", "item": "pickaxe"}
    assert "it must be false now" in llm.prompt(1)


def test_no_usable_predicate_means_no_attempt(tmp_path: Path) -> None:
    agent, llm = make_agent(tmp_path, ["<predicate>nope</predicate>", "no tags at all"])
    outcome = asyncio.run(agent.solve(task(None), FakeGame(), trace_id="t"))
    assert (outcome.verdict, outcome.reason) == (Verdict.UNKNOWN, "no usable predicate")
    assert len(llm.requests) == 2


def test_a_frozen_library_uses_skills_but_learns_nothing(tmp_path: Path) -> None:
    agent, _ = make_agent(tmp_path, [answer("makePickaxe", "GIVE pickaxe")], learn=False)
    outcome = asyncio.run(agent.solve(task(), FakeGame(), trace_id="t"))
    assert outcome.verdict is Verdict.TRUE
    assert outcome.learned_skill is None
    assert agent.library.all() == []


def test_every_llm_call_is_in_the_runs_trace(tmp_path: Path) -> None:
    agent, _ = make_agent(
        tmp_path, [answer("makePickaxe", "THROW"), answer("makePickaxe", "GIVE pickaxe")]
    )
    asyncio.run(agent.solve(task(), FakeGame(), trace_id="trace-42"))
    lines = (tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["trace_id"] for line in lines] == ["trace-42", "trace-42"]


def test_parse_skill_strips_code_fences() -> None:
    draft = parse_skill(
        "<name>doIt</name><description>d</description><code>```js\nreturn 1;\n```</code>"
    )
    assert draft.code == "return 1;"


def test_load_task(tmp_path: Path) -> None:
    path = tmp_path / "t.json"
    path.write_text(
        json.dumps({"id": "a", "goal": "Do it.", "predicate": HAS_PICKAXE, "timeoutS": 90}),
        encoding="utf-8",
    )
    loaded = load_task(path)
    assert (loaded.id, loaded.timeout_s, loaded.predicate_spec) == ("a", 90.0, HAS_PICKAXE)
    path.write_text(json.dumps({"id": "a", "goal": ""}), encoding="utf-8")
    with pytest.raises(TaskError, match="goal"):
        load_task(path)
