"""The Anthropic adapter against a mocked HTTP transport: no network, no API key."""

import asyncio
import json

import anthropic
import httpx2
import pytest

from agent_core.llm import LlmError, LlmRequest, Message
from agent_core.llm.anthropic_backend import FALLBACK_BETA, AnthropicBackend


def make_backend(handler: "httpx2.MockTransport") -> AnthropicBackend:
    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=handler),
    )
    return AnthropicBackend(client)


def request(model: str) -> LlmRequest:
    return LlmRequest(
        model=model,
        system="be brief",
        messages=[Message("user", "hi")],
        max_tokens=100,
        effort="low",
        timeout_s=5,
    )


MESSAGE_BODY: dict[str, object] = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-5-5",
    "content": [{"type": "text", "text": "Hello "}, {"type": "text", "text": "there"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {
        "input_tokens": 12,
        "output_tokens": 3,
        "cache_read_input_tokens": 100,
        "cache_creation_input_tokens": 0,
    },
}


def test_sonnet_request_opts_into_fallback_and_parses_the_answer() -> None:
    seen: list[httpx2.Request] = []

    def handle(http_request: httpx2.Request) -> httpx2.Response:
        seen.append(http_request)
        return httpx2.Response(200, json=MESSAGE_BODY, headers={"request-id": "req_42"})

    result = asyncio.run(
        make_backend(httpx2.MockTransport(handle)).create(request("claude-sonnet-5-5"))
    )

    body = json.loads(seen[0].content)
    assert body["fallbacks"] == "default"
    assert body["output_config"] == {"effort": "low"}
    assert body["system"] == "be brief"
    assert FALLBACK_BETA in seen[0].headers["anthropic-beta"]
    assert result.text == "Hello there"
    assert result.usage.cache_read_tokens == 100
    assert result.request_id == "req_42"
    assert result.fallback_used is False


def test_haiku_request_has_no_fallback() -> None:
    seen: list[httpx2.Request] = []

    def handle(http_request: httpx2.Request) -> httpx2.Response:
        seen.append(http_request)
        return httpx2.Response(200, json={**MESSAGE_BODY, "model": "claude-haiku-5-5"})

    asyncio.run(make_backend(httpx2.MockTransport(handle)).create(request("claude-haiku-5-5")))
    assert "fallbacks" not in json.loads(seen[0].content)


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "check ANTHROPIC_API_KEY"), (404, "Unknown model"), (500, "API error 500")],
)
def test_http_errors_become_llm_errors(status: int, message: str) -> None:
    def handle(_: httpx2.Request) -> httpx2.Response:
        error = {"type": "error", "error": {"type": "x", "message": "nope"}}
        return httpx2.Response(status, json=error)

    with pytest.raises(LlmError, match=message):
        asyncio.run(make_backend(httpx2.MockTransport(handle)).create(request("claude-haiku-5-5")))


def test_missing_credentials_give_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    client = anthropic.AsyncAnthropic(
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(
            transport=httpx2.MockTransport(lambda _: httpx2.Response(500))
        ),
    )
    with pytest.raises(LlmError, match="No Anthropic credentials"):
        asyncio.run(AnthropicBackend(client).create(request("claude-haiku-5-5")))
