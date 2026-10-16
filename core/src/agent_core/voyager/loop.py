"""The Voyager loop for one task (plan P2.4).

    predicate (given, or written by the LLM first and checked to be false now)
    → for each attempt (at most `max_attempts`):
        observe → retrieve library skills → LLM writes a skill → run it in the plugin's executor
        → the predicate decides → success: store the skill; failure: feed the reason back
The skill's own report never counts as success; only the predicate does (AGENTS.md decision 6).
"""

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from agent_core.library import LibraryError, SkillLibrary
from agent_core.llm import LlmClient, LlmError, ModelRole
from agent_core.plugins import JsonObject, JsonValue, PluginClient, PluginError
from agent_core.skills import SkillResult, run_skill
from agent_core.verifier import Predicate, PredicateError, Verdict, evaluate, parse_predicate
from agent_core.voyager.prompts import (
    DraftError,
    Feedback,
    parse_predicate_answer,
    parse_skill,
    predicate_prompt,
    skill_system_prompt,
    skill_user_prompt,
)
from agent_core.voyager.task import Task

_log = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
LIBRARY_RESULTS = 3
# The game reports inventory changes a few ticks after a skill returns.
VERDICT_WAIT_S = 3.0
VERDICT_POLL_S = 0.25


class GameSession(Protocol):
    async def observe(self) -> JsonObject: ...

    async def run_skill(self, code: str, timeout_s: float) -> SkillResult: ...


@dataclass(frozen=True, slots=True)
class PluginSession:
    """A `GameSession` over a running plugin's main process."""

    plugin: PluginClient

    async def observe(self) -> JsonObject:
        return await self.plugin.observe()

    async def run_skill(self, code: str, timeout_s: float) -> SkillResult:
        return await run_skill(self.plugin, code, timeout_s=timeout_s)


@dataclass(frozen=True, slots=True)
class Attempt:
    number: int
    skill_name: str | None
    status: str  # draft-error | ok | error | timeout | cancelled | crashed
    verdict: Verdict
    problem: str | None
    duration_s: float
    used_skills: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskOutcome:
    task_id: str
    verdict: Verdict
    attempts: tuple[Attempt, ...]
    predicate: JsonValue
    learned_skill: str | None = None
    used_skills: tuple[str, ...] = ()
    reason: str | None = None


@dataclass(slots=True)
class VoyagerAgent:
    llm: LlmClient
    library: SkillLibrary
    skill_api: Sequence[JsonObject]
    guide: str
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    # False for a frozen library (evaluation): skills are used but never stored (decision 14).
    learn: bool = True
    _system: str = field(init=False, default="")

    def __post_init__(self) -> None:
        self._system = skill_system_prompt(self.skill_api, self.guide)

    async def solve(self, task: Task, session: GameSession, *, trace_id: str) -> TaskOutcome:
        start = await session.observe()
        predicate, spec = await self._predicate(task, start, trace_id)
        if predicate is None:
            return TaskOutcome(task.id, Verdict.UNKNOWN, (), spec, reason="no usable predicate")
        initial = evaluate(predicate, start)
        if initial is not Verdict.FALSE:
            # Nothing a skill does could be credited: the goal already holds, or cannot be judged.
            reason = f"predicate is {initial} before any attempt"
            return TaskOutcome(task.id, Verdict.UNKNOWN, (), spec, reason=reason)

        attempts: list[Attempt] = []
        feedback: list[Feedback] = []
        for number in range(1, self.max_attempts + 1):
            began = time.monotonic()
            observation = start if number == 1 else await session.observe()
            retrieved = self.library.search(task.goal, k=LIBRARY_RESULTS)
            answer = await self.llm.complete(
                skill_user_prompt(task.goal, spec, observation, retrieved, feedback),
                role=ModelRole.CODE,
                purpose="voyager.write_skill",
                system=self._system,
                trace_id=trace_id,
            )
            try:
                draft = parse_skill(answer.text)
            except DraftError as error:
                problem = f"the answer could not be used: {error}"
                attempts.append(
                    Attempt(number, None, "draft-error", Verdict.FALSE, problem, _since(began))
                )
                feedback.append(Feedback(number, answer.text[:2_000], problem))
                continue

            code, used = self.library.assemble(draft.code)
            result = await session.run_skill(code, task.timeout_s)
            verdict, after = await _judge(session, predicate)
            attempt = Attempt(
                number,
                draft.name,
                result.status,
                verdict,
                None if verdict is Verdict.TRUE else _problem(result, verdict),
                _since(began),
                tuple(used),
            )
            attempts.append(attempt)
            if verdict is Verdict.TRUE:
                learned = self._store(draft.name, draft.description, draft.code, task.id, used)
                return TaskOutcome(
                    task.id, Verdict.TRUE, tuple(attempts), spec, learned, tuple(used)
                )
            feedback.append(Feedback(number, draft.code, attempt.problem or "", result.logs, after))
        return TaskOutcome(task.id, Verdict.FALSE, tuple(attempts), spec, reason="out of attempts")

    def _store(
        self, name: str, description: str, code: str, task_id: str, used: list[str]
    ) -> str | None:
        self.library.record_use(used)
        if not self.learn:
            return None
        try:
            return self.library.add(name, description, code, task_id).name
        except LibraryError:
            return None

    async def _predicate(
        self, task: Task, observation: JsonObject, trace_id: str
    ) -> tuple[Predicate | None, JsonValue]:
        """The task's predicate, or one the LLM writes now, before any code (decision 6)."""
        if task.predicate is not None:
            return task.predicate, task.predicate_spec
        problem = ""
        for _ in range(2):
            prompt = predicate_prompt(task.goal, observation)
            if problem:
                prompt += f"\n\nYour previous answer was rejected: {problem}"
            try:
                answer = await self.llm.complete(
                    prompt,
                    role=ModelRole.CODE,
                    purpose="voyager.write_predicate",
                    trace_id=trace_id,
                )
                spec = parse_predicate_answer(answer.text)
                predicate = parse_predicate(spec)
            except (DraftError, PredicateError, LlmError) as error:
                problem = str(error)
                continue
            verdict = evaluate(predicate, observation)
            if verdict is Verdict.FALSE:
                return predicate, spec
            problem = f"it is {verdict} on the current observation; it must be false now"
        return None, None


async def _judge(session: GameSession, predicate: Predicate) -> tuple[Verdict, JsonObject | None]:
    deadline = time.monotonic() + VERDICT_WAIT_S
    after: JsonObject | None = None
    verdict = Verdict.UNKNOWN
    while True:
        try:
            after = await session.observe()
        except PluginError as error:
            # A plugin that died during the skill: the attempt failed, the verdict is unknown.
            _log.warning("cannot observe after the skill: %s", error)
            return Verdict.UNKNOWN, after
        verdict = evaluate(predicate, after)
        if verdict is Verdict.TRUE or time.monotonic() >= deadline:
            return verdict, after
        await asyncio.sleep(VERDICT_POLL_S)


def _problem(result: SkillResult, verdict: Verdict) -> str:
    if result.status == "ok":
        return f"the skill returned {result.result!r}, but the predicate is {verdict}"
    return f"the skill ended with {result.status}: {result.error}; the predicate is {verdict}"


def _since(began: float) -> float:
    return round(time.monotonic() - began, 2)
