"""The Voyager loop for one task (plan P2.4).

    predicate (given, or written by the LLM first and checked to be false now)
    → for each attempt (at most `max_attempts`, within a time budget):
        reset (from attempt 2 on) → observe → retrieve library skills → LLM writes a skill
        → cheap checks (format, names, syntax) → run it in the plugin's executor
        → the predicate decides → success: store the skill; failure: feed the reason back
The skill's own report never counts as success; only the predicate does (AGENTS.md decision 6).
A skill is stored only when it also ran cleanly, so the library holds exactly what was verified.
"""

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from agent_core.library import LibraryError, SkillLibrary, calls
from agent_core.llm import LlmClient, LlmError, ModelRole
from agent_core.plugins import JsonObject, JsonValue, PluginClient, PluginError
from agent_core.skills import SkillResult, SkillRunError, run_skill
from agent_core.verifier import Predicate, PredicateError, Verdict, evaluate, parse_predicate
from agent_core.voyager.prompts import (
    DraftError,
    Feedback,
    SkillDraft,
    api_names,
    parse_predicate_answer,
    parse_skill,
    predicate_prompt,
    skill_system_prompt,
    skill_user_prompt,
)
from agent_core.voyager.task import Task

_log = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
MAX_ATTEMPTS_LIMIT = 6
DEFAULT_TASK_BUDGET_S = 1_200.0
LIBRARY_RESULTS = 3
# The game reports inventory changes a few ticks after a skill returns.
VERDICT_WAIT_S = 3.0
VERDICT_POLL_S = 0.25
SETTLE_WAIT_S = 3.0

PredicateSource = Literal["task", "llm", "none"]
# Why a run cannot count either way: these are left out of success rates.
InvalidReason = Literal["no_predicate", "already_true", "predicate_unknown"]


class GameSession(Protocol):
    async def observe(self) -> JsonObject: ...

    async def run_skill(self, code: str, timeout_s: float) -> SkillResult: ...

    async def check(self, code: str) -> str | None:
        """Why the code can never run (syntax, forbidden constructs), or None."""
        ...

    async def reset(self) -> bool:
        """Back to the task's start state before another attempt; False if it cannot."""
        ...


@dataclass(frozen=True, slots=True)
class PluginSession:
    """A `GameSession` over a running plugin's main process and its scenario component."""

    plugin: PluginClient
    scenario: PluginClient | None = None
    reset_params: JsonObject = field(default_factory=dict[str, JsonValue])
    setup: JsonObject = field(default_factory=dict[str, JsonValue])

    async def observe(self) -> JsonObject:
        return await self.plugin.observe()

    async def run_skill(self, code: str, timeout_s: float) -> SkillResult:
        return await run_skill(self.plugin, code, timeout_s=timeout_s)

    async def check(self, code: str) -> str | None:
        reply = await self.plugin.request("skill.check", {"code": code})
        problem = reply.get("problem") if isinstance(reply, dict) else None
        return problem if isinstance(problem, str) else None

    async def reset(self) -> bool:
        if self.scenario is None:
            return False
        player = (await self.plugin.observe({"nearby": False})).get("username")
        await self.scenario.request("scenario.reset", {**self.reset_params, "player": player})
        if self.setup:
            await self.scenario.request("scenario.setup", {"player": player, "spec": self.setup})
        return True


@dataclass(frozen=True, slots=True)
class Attempt:
    number: int
    skill_name: str | None
    # draft-error | check-error | llm-error | plugin-error (before running), or the skill's
    # own status: ok | error | timeout | cancelled | crashed
    status: str
    verdict: Verdict
    problem: str | None
    duration_s: float
    used_skills: tuple[str, ...] = ()
    code: str | None = None
    # False when the attempt ran on what an earlier attempt left behind (no reset available).
    clean_start: bool = True


@dataclass(frozen=True, slots=True)
class TaskOutcome:
    task_id: str
    verdict: Verdict
    attempts: tuple[Attempt, ...]
    predicate: JsonValue
    predicate_source: PredicateSource = "task"
    learned_skill: str | None = None
    used_skills: tuple[str, ...] = ()
    reason: str | None = None
    invalid: InvalidReason | None = None


@dataclass(frozen=True, slots=True)
class _Step:
    attempt: Attempt
    feedback: Feedback | None = None
    draft: SkillDraft | None = None


@dataclass(slots=True)
class VoyagerAgent:
    llm: LlmClient
    library: SkillLibrary
    skill_api: Sequence[JsonObject]
    guide: str
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    # False for a frozen library (evaluation): skills are used but never stored (decision 14).
    learn: bool = True
    task_budget_s: float = DEFAULT_TASK_BUDGET_S
    _system: str = field(init=False, default="")
    _api_names: set[str] = field(init=False, default_factory=set[str])

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= MAX_ATTEMPTS_LIMIT:
            raise ValueError(f"max_attempts must be from 1 to {MAX_ATTEMPTS_LIMIT}")
        self._system = skill_system_prompt(self.skill_api, self.guide)
        self._api_names = api_names(self.skill_api)

    async def solve(self, task: Task, session: GameSession, *, trace_id: str) -> TaskOutcome:
        deadline = time.monotonic() + self.task_budget_s
        start = await _settled(session)
        predicate, spec, source = await self._predicate(task, start, trace_id)
        if predicate is None:
            return TaskOutcome(
                task.id, Verdict.UNKNOWN, (), spec, source,
                reason="no usable predicate", invalid="no_predicate",
            )  # fmt: skip
        initial = evaluate(predicate, start)
        if initial is not Verdict.FALSE:
            # Nothing a skill does could be credited: the goal already holds, or cannot be judged.
            return TaskOutcome(
                task.id, Verdict.UNKNOWN, (), spec, source,
                reason=f"predicate is {initial} before any attempt",
                invalid="already_true" if initial is Verdict.TRUE else "predicate_unknown",
            )  # fmt: skip

        attempts: list[Attempt] = []
        feedback: list[Feedback] = []
        for number in range(1, self.max_attempts + 1):
            if time.monotonic() >= deadline:
                break
            began = time.monotonic()
            try:
                clean = True if number == 1 else await session.reset()
                observation = start if number == 1 else await _settled(session)
                step = await self._attempt(
                    number, task, spec, predicate, observation, session, feedback, trace_id, clean
                )
            except (PluginError, TimeoutError) as error:
                # The plugin is gone or stuck: further attempts cannot run in this session.
                attempts.append(
                    Attempt(
                        number, None, "plugin-error", Verdict.UNKNOWN, str(error), _since(began)
                    )
                )
                return TaskOutcome(
                    task.id, Verdict.UNKNOWN, tuple(attempts), spec, source,
                    reason=f"plugin failed: {error}",
                )  # fmt: skip
            attempts.append(step.attempt)
            if step.draft is not None:
                learned = self._store(task.id, step.draft, step.attempt.used_skills)
                return TaskOutcome(
                    task.id, Verdict.TRUE, tuple(attempts), spec, source,
                    learned, step.attempt.used_skills,
                )  # fmt: skip
            if step.feedback is not None:
                feedback.append(step.feedback)
        reason = "out of attempts" if len(attempts) == self.max_attempts else "out of time"
        return TaskOutcome(task.id, Verdict.FALSE, tuple(attempts), spec, source, reason=reason)

    async def _attempt(
        self,
        number: int,
        task: Task,
        spec: JsonValue,
        predicate: Predicate,
        observation: JsonObject,
        session: GameSession,
        feedback: Sequence[Feedback],
        trace_id: str,
        clean: bool,
    ) -> _Step:
        began = time.monotonic()
        retrieved = self.library.search(task.goal, k=LIBRARY_RESULTS)
        names = [skill.name for skill in self.library.all()]
        try:
            answer = await self.llm.complete(
                skill_user_prompt(task.goal, spec, observation, retrieved, feedback, names),
                role=ModelRole.CODE,
                purpose=f"voyager.write_skill#{number}",
                system=self._system,
                trace_id=trace_id,
            )
        except LlmError as error:
            problem = f"no answer from the model: {error}"
            return _Step(Attempt(number, None, "llm-error", Verdict.FALSE, problem, _since(began)))

        try:
            if answer.truncated:
                raise DraftError("the answer was cut off (too long); write a shorter skill")
            draft = parse_skill(answer.text)
            self._check_names(draft)
            code, used = self.library.assemble(draft.code)
        except (DraftError, LibraryError) as error:
            problem = f"the answer could not be used: {error}"
            attempt = Attempt(number, None, "draft-error", Verdict.FALSE, problem, _since(began))
            return _Step(attempt, Feedback(number, answer.text[:3_000], problem))

        # A syntax error or forbidden construct costs no game time: refused before running.
        refusal = await session.check(code)
        if refusal is not None:
            problem = f"the code cannot run: {refusal}"
            attempt = Attempt(
                number, draft.name, "check-error", Verdict.FALSE, problem, _since(began),
                tuple(used), draft.code, clean,
            )  # fmt: skip
            return _Step(attempt, Feedback(number, draft.code, problem, skill_name=draft.name))

        try:
            result = await session.run_skill(code, task.timeout_s)
        except SkillRunError as error:
            raise PluginError(f"skill run failed: {error}") from error
        verdict, after = await _judge(session, predicate)
        # Stored and counted only when the predicate holds AND the skill ran to its end cleanly.
        ok = verdict is Verdict.TRUE and result.status == "ok"
        attempt = Attempt(
            number, draft.name, result.status, verdict, None if ok else _problem(result, verdict),
            _since(began), tuple(used), draft.code, clean,
        )  # fmt: skip
        if ok:
            return _Step(attempt, draft=draft)
        more = Feedback(
            number, draft.code, attempt.problem or "", result.logs, after, draft.name, result.result
        )
        return _Step(attempt, more)

    def _check_names(self, draft: SkillDraft) -> None:
        if draft.name in self._api_names:
            raise DraftError(f"{draft.name} is an API name; choose another name for the skill")
        if self.library.get(draft.name) is not None:
            raise DraftError(
                f"a library skill is already called {draft.name}; call it, or choose a new name"
            )
        if calls(draft.code, draft.name):
            raise DraftError(f"the skill {draft.name} must not call itself")

    def _store(self, task_id: str, draft: SkillDraft, used: Sequence[str]) -> str | None:
        self.library.record_use(used)
        if not self.learn:
            return None
        try:
            return self.library.add(draft.name, draft.description, draft.code, task_id).name
        except LibraryError as error:
            _log.warning("verified skill %s not stored: %s", draft.name, error)
            return None

    async def _predicate(
        self, task: Task, observation: JsonObject, trace_id: str
    ) -> tuple[Predicate | None, JsonValue, PredicateSource]:
        """The task's predicate, or one the LLM writes now, before any code (decision 6)."""
        if task.predicate is not None:
            return task.predicate, task.predicate_spec, "task"
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
                return predicate, spec, "llm"
            problem = f"it is {verdict} on the current observation; it must be false now"
        return None, None, "none"


async def _settled(session: GameSession) -> JsonObject:
    """An observation that two reads in a row agree on, so a reset or setup has arrived."""
    deadline = time.monotonic() + SETTLE_WAIT_S
    previous = await session.observe()
    while time.monotonic() < deadline:
        await asyncio.sleep(VERDICT_POLL_S)
        current = await session.observe()
        if current.get("inventory") == previous.get("inventory"):
            return current
        previous = current
    return previous


async def _judge(session: GameSession, predicate: Predicate) -> tuple[Verdict, JsonObject | None]:
    deadline = time.monotonic() + VERDICT_WAIT_S
    after: JsonObject | None = None
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
    if verdict is Verdict.TRUE:
        # The goal holds, but the skill crashed or timed out: not clean enough to store or count.
        return f"the goal holds, but the skill ended with {result.status}: {result.error}"
    if result.status == "ok":
        return f"the skill returned normally, but the predicate is {verdict}"
    return f"the skill ended with {result.status}: {result.error}; the predicate is {verdict}"


def _since(began: float) -> float:
    return round(time.monotonic() - began, 2)
