import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agent_core.llm import (
    BackendResult,
    LlmClient,
    LlmError,
    LlmRefusalError,
    LlmRequest,
    Message,
    ModelRole,
    Usage,
)
from agent_core.telemetry import TelemetryRecorder


@dataclass
class FakeBackend:
    result: BackendResult | None = None
    error: Exception | None = None
    provider: str = "fake"
    requests: list[LlmRequest] = field(default_factory=list[LlmRequest])

    async def create(self, request: LlmRequest) -> BackendResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def ok_result(model: str = "claude-haiku-5-5", **overrides: object) -> BackendResult:
    fields: dict[str, object] = {
        "text": "hello",
        "served_model": model,
        "stop_reason": "end_turn",
        "usage": Usage(input_tokens=1_000, output_tokens=200),
        "request_id": "req_1",
    }
    fields.update(overrides)
    return BackendResult(**fields)  # pyright: ignore[reportArgumentType]


def read_records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def make_client(tmp_path: Path, backend: FakeBackend) -> tuple[LlmClient, Path]:
    path = tmp_path / "telemetry.jsonl"
    return LlmClient(backend, TelemetryRecorder(path), timeout_s=30), path


def test_text_role_uses_haiku_and_records_cost(tmp_path: Path) -> None:
    backend = FakeBackend(result=ok_result())
    client, path = make_client(tmp_path, backend)

    response = asyncio.run(
        client.complete("hi", role=ModelRole.TEXT, purpose="test.text", trace_id="t1")
    )

    assert backend.requests[0].model == "claude-haiku-5-5"
    assert backend.requests[0].messages == [Message("user", "hi")]
    assert backend.requests[0].timeout_s == 30
    assert response.text == "hello"
    # 1000 * $0.10/M + 200 * $0.50/M
    assert response.cost_usd == pytest.approx(0.0002)
    [record] = read_records(path)
    assert record["trace_id"] == "t1"
    assert record["purpose"] == "test.text"
    assert record["ok"] is True
    assert record["cost_usd"] == pytest.approx(0.0002)
    assert record["input_tokens"] == 1000
    assert record["request_id"] == "req_1"


def test_code_role_uses_sonnet(tmp_path: Path) -> None:
    backend = FakeBackend(result=ok_result("claude-sonnet-5-5"))
    client, _ = make_client(tmp_path, backend)
    asyncio.run(
        client.complete("write code", role=ModelRole.CODE, purpose="test.code", effort="high")
    )
    assert backend.requests[0].model == "claude-sonnet-5-5"
    assert backend.requests[0].effort == "high"


def test_fallback_is_priced_at_the_serving_model(tmp_path: Path) -> None:
    backend = FakeBackend(result=ok_result("claude-sonnet-5", fallback_used=True))
    client, path = make_client(tmp_path, backend)
    response = asyncio.run(client.complete("x", role=ModelRole.CODE, purpose="test"))
    # claude-sonnet-5 is not in the price table: the cost is unknown, never a guess.
    assert response.cost_usd is None
    [record] = read_records(path)
    assert (record["requested_model"], record["served_model"]) == (
        "claude-sonnet-5-5",
        "claude-sonnet-5",
    )
    assert record["fallback_used"] is True


def test_refusal_is_recorded_and_raised(tmp_path: Path) -> None:
    backend = FakeBackend(result=ok_result(stop_reason="refusal", refusal_category="cyber"))
    client, path = make_client(tmp_path, backend)
    with pytest.raises(LlmRefusalError, match="category: cyber") as caught:
        asyncio.run(client.complete("x", role=ModelRole.TEXT, purpose="test"))
    assert caught.value.category == "cyber"
    [record] = read_records(path)
    assert record["ok"] is False
    assert record["error_type"] == "refusal"


def test_backend_error_is_recorded_and_reraised(tmp_path: Path) -> None:
    backend = FakeBackend(error=LlmError("no answer within 30 s."))
    client, path = make_client(tmp_path, backend)
    with pytest.raises(LlmError, match="no answer"):
        asyncio.run(client.complete("x", role=ModelRole.TEXT, purpose="test"))
    [record] = read_records(path)
    assert record["ok"] is False
    assert record["error_type"] == "LlmError"
    assert record["served_model"] is None
    assert record["cost_usd"] is None


def test_truncation_is_visible(tmp_path: Path) -> None:
    backend = FakeBackend(result=ok_result(stop_reason="max_tokens"))
    client, _ = make_client(tmp_path, backend)
    response = asyncio.run(client.complete("x", role=ModelRole.TEXT, purpose="test"))
    assert response.truncated


def test_calls_in_one_trace_share_the_id(tmp_path: Path) -> None:
    backend = FakeBackend(result=ok_result())
    client, path = make_client(tmp_path, backend)

    async def two_calls() -> None:
        first = await client.complete("a", role=ModelRole.TEXT, purpose="step1")
        await client.complete("b", role=ModelRole.TEXT, purpose="step2", trace_id=first.trace_id)

    asyncio.run(two_calls())
    first, second = read_records(path)
    assert first["trace_id"] == second["trace_id"]


def test_empty_conversation_is_rejected(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path, FakeBackend(result=ok_result()))
    with pytest.raises(ValueError, match="at least one message"):
        asyncio.run(client.complete([], role=ModelRole.TEXT, purpose="test"))
