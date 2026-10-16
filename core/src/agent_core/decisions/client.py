"""The L1 `DecisionClient` (decisions 10, 10c, 10d).

A decision point is a versioned `ChoiceQuestion`: instructions, options, an acceptance threshold.
Providers are tried in order (e.g. Jev, then a keyword rule): a provider that fails or times out
hands over to the next. A decision is *accepted* only when its confidence reaches the question's
threshold; otherwise the caller escalates (to L2). Confidence is never permission (plan P3.4).

Every call is logged as one JSON line (question, version, provider, model, choice, probabilities,
confidence, latency, the state): the benchmark and fine-tuning data for L1 (decision 10c).
"""

import asyncio
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from agent_core.plugins import JsonObject, JsonValue
from agent_core.telemetry import JsonlWriter


class DecisionError(Exception):
    """A provider could not answer (service error, timeout, bad response)."""


@dataclass(frozen=True, slots=True)
class ChoiceQuestion:
    id: str
    version: int
    instructions: str
    options: Mapping[str, str]  # name → description
    threshold: float
    # Words that point to an option, for the keyword rule fallback.
    keywords: Mapping[str, Sequence[str]] = field(default_factory=dict[str, Sequence[str]])


@dataclass(frozen=True, slots=True)
class ProviderAnswer:
    choice: str
    probabilities: Mapping[str, float]
    confidence: float
    model: str


class ChoiceProvider(Protocol):
    name: str

    async def choose(self, question: ChoiceQuestion, state: JsonObject) -> ProviderAnswer: ...


@dataclass(frozen=True, slots=True)
class Decision:
    question_id: str
    version: int
    choice: str | None
    confidence: float
    accepted: bool
    provider: str | None
    model: str | None
    latency_ms: float
    probabilities: Mapping[str, float] = field(default_factory=dict[str, float])
    # Providers tried before the one that answered, with why they did not.
    fell_back: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    trace_id: str | None
    question_id: str
    version: int
    provider: str | None
    model: str | None
    choice: str | None
    confidence: float
    accepted: bool
    threshold: float
    latency_ms: float
    probabilities: Mapping[str, float]
    fell_back: tuple[str, ...]
    state: JsonObject
    shadow: bool
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DecisionClient:
    def __init__(
        self,
        providers: Sequence[ChoiceProvider],
        log_path: Path,
        *,
        timeout_s: float = 2.0,
    ) -> None:
        if not providers:
            raise ValueError("a DecisionClient needs at least one provider")
        self._providers = list(providers)
        self._log = JsonlWriter(log_path)
        self._timeout_s = timeout_s

    async def decide(
        self,
        question: ChoiceQuestion,
        state: JsonObject,
        *,
        trace_id: str | None = None,
        shadow: bool = False,
    ) -> Decision:
        started = time.perf_counter()
        fell_back: list[str] = []
        decision: Decision | None = None
        for provider in self._providers:
            try:
                async with asyncio.timeout(self._timeout_s):
                    answer = await provider.choose(question, state)
            except (DecisionError, TimeoutError) as error:
                fell_back.append(f"{provider.name}: {error or 'timeout'}")
                continue
            if answer.choice not in question.options:
                fell_back.append(f"{provider.name}: answered unknown option {answer.choice!r}")
                continue
            decision = Decision(
                question.id,
                question.version,
                answer.choice,
                answer.confidence,
                answer.confidence >= question.threshold,
                provider.name,
                answer.model,
                _ms(started),
                dict(answer.probabilities),
                tuple(fell_back),
            )
            break
        if decision is None:
            decision = Decision(
                question.id, question.version, None, 0.0, False, None, None, _ms(started),
                fell_back=tuple(fell_back),
            )  # fmt: skip
        self._log.write(
            DecisionRecord(
                trace_id,
                question.id,
                question.version,
                decision.provider,
                decision.model,
                decision.choice,
                decision.confidence,
                decision.accepted,
                question.threshold,
                decision.latency_ms,
                decision.probabilities,
                decision.fell_back,
                state,
                shadow,
            )
        )
        return decision


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def json_state(value: Mapping[str, JsonValue]) -> JsonObject:
    return dict(value)
