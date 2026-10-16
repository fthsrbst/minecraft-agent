"""The single entry point for L2 calls: picks a model per role, measures, records every call.

The provider SDK lives behind `LlmBackend`, so tests use a fake backend and a second provider
would be one more adapter, not changes here.
"""

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from agent_core.llm.pricing import Usage, cost_usd
from agent_core.telemetry import LlmCallRecord, TelemetryRecorder, new_trace_id


class ModelRole(StrEnum):
    # Code writing and repair, planning, skill induction, critic (AGENTS.md decision 5).
    CODE = "code"
    # High-volume text: summaries, diary, skill descriptions.
    TEXT = "text"


DEFAULT_MODELS: Mapping[ModelRole, str] = {
    ModelRole.CODE: "claude-sonnet-5-5",
    ModelRole.TEXT: "claude-haiku-5-5",
}

type Effort = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class LlmRequest:
    model: str
    system: str
    messages: Sequence[Message]
    max_tokens: int
    effort: Effort | None
    timeout_s: float


@dataclass(frozen=True, slots=True)
class BackendResult:
    text: str
    served_model: str
    stop_reason: str | None
    usage: Usage
    request_id: str | None = None
    refusal_category: str | None = None
    fallback_used: bool = False


class LlmBackend(Protocol):
    provider: str

    async def create(self, request: LlmRequest) -> BackendResult: ...


class LlmError(Exception):
    """An LLM call failed; the message says why and what to check."""


class LlmRefusalError(LlmError):
    def __init__(self, model: str, category: str | None) -> None:
        super().__init__(f"{model} declined the request (category: {category or 'unknown'}).")
        self.category = category


@dataclass(frozen=True, slots=True)
class LlmResponse:
    text: str
    model: str
    stop_reason: str | None
    usage: Usage
    cost_usd: float | None
    latency_ms: float
    trace_id: str

    @property
    def truncated(self) -> bool:
        return self.stop_reason == "max_tokens"


class LlmClient:
    def __init__(
        self,
        backend: LlmBackend,
        telemetry: TelemetryRecorder,
        *,
        models: Mapping[ModelRole, str] = DEFAULT_MODELS,
        timeout_s: float = 300.0,
    ) -> None:
        self._backend = backend
        self._telemetry = telemetry
        self._models = models
        self._timeout_s = timeout_s

    async def complete(
        self,
        prompt: str | Sequence[Message],
        *,
        role: ModelRole,
        purpose: str,
        system: str = "",
        max_tokens: int = 16_000,
        effort: Effort | None = None,
        trace_id: str | None = None,
    ) -> LlmResponse:
        """Sends one request. `purpose` names the caller (e.g. "skill.write") for the report."""
        messages = [Message("user", prompt)] if isinstance(prompt, str) else list(prompt)
        if not messages:
            raise ValueError("complete() needs at least one message.")
        model = self._models[role]
        trace = trace_id or new_trace_id()
        request = LlmRequest(model, system, messages, max_tokens, effort, self._timeout_s)

        started = time.perf_counter()
        try:
            result = await self._backend.create(request)
        except Exception as error:
            self._telemetry.record(
                LlmCallRecord(
                    trace_id=trace,
                    purpose=purpose,
                    provider=self._backend.provider,
                    requested_model=model,
                    served_model=None,
                    ok=False,
                    latency_ms=_elapsed_ms(started),
                    error_type=type(error).__name__,
                    error_message=str(error)[:500],
                )
            )
            raise
        latency_ms = _elapsed_ms(started)

        # A fallback answer is billed at the serving model's prices.
        cost = cost_usd(result.served_model, result.usage)
        refused = result.stop_reason == "refusal"
        self._telemetry.record(
            LlmCallRecord(
                trace_id=trace,
                purpose=purpose,
                provider=self._backend.provider,
                requested_model=model,
                served_model=result.served_model,
                ok=not refused,
                latency_ms=latency_ms,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                cache_read_tokens=result.usage.cache_read_tokens,
                cache_write_tokens=result.usage.cache_write_tokens,
                cost_usd=cost,
                stop_reason=result.stop_reason,
                fallback_used=result.fallback_used,
                request_id=result.request_id,
                error_type="refusal" if refused else None,
                error_message=result.refusal_category if refused else None,
            )
        )
        if refused:
            raise LlmRefusalError(result.served_model, result.refusal_category)

        return LlmResponse(
            text=result.text,
            model=result.served_model,
            stop_reason=result.stop_reason,
            usage=result.usage,
            cost_usd=cost,
            latency_ms=latency_ms,
            trace_id=trace,
        )


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
