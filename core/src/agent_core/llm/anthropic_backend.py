"""`LlmBackend` for the Anthropic API. The only module that imports the `anthropic` SDK."""

import anthropic
from anthropic.types.beta import BetaMessage, BetaMessageParam

from agent_core.llm.client import BackendResult, LlmError, LlmRequest
from agent_core.llm.pricing import Usage

# Server-side refusal fallback ("default" picks Anthropic's recommended model per refusal category).
# Haiku 5.5 has no server-side fallback, so the parameter is sent only for these models.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MODELS_WITH_FALLBACK = frozenset({"claude-opus-5-5", "claude-sonnet-5-5"})


class AnthropicBackend:
    provider = "anthropic"

    def __init__(
        self, client: anthropic.AsyncAnthropic | None = None, *, max_retries: int = 2
    ) -> None:
        # The SDK reads ANTHROPIC_API_KEY from the environment; our code never handles the key.
        self._client = client or anthropic.AsyncAnthropic(max_retries=max_retries)

    async def create(self, request: LlmRequest) -> BackendResult:
        messages: list[BetaMessageParam] = [
            {"role": m.role, "content": m.content} for m in request.messages
        ]
        client = self._client.with_options(timeout=request.timeout_s)
        use_fallback = request.model in MODELS_WITH_FALLBACK
        try:
            message = await client.beta.messages.create(
                model=request.model,
                max_tokens=request.max_tokens,
                system=request.system or anthropic.omit,
                messages=messages,
                output_config={"effort": request.effort} if request.effort else anthropic.omit,
                betas=[FALLBACK_BETA] if use_fallback else anthropic.omit,
                fallbacks="default" if use_fallback else anthropic.omit,
            )
        except TypeError as error:
            # The SDK reports missing credentials as a TypeError before any request is sent.
            if "authentication method" not in str(error):
                raise
            raise LlmError(
                "No Anthropic credentials: set ANTHROPIC_API_KEY in .env (see .env.example)."
            ) from error
        except anthropic.APITimeoutError as error:
            raise LlmError(f"{request.model}: no answer within {request.timeout_s:g} s.") from error
        except anthropic.AuthenticationError as error:
            raise LlmError(
                "Anthropic rejected the API key; check ANTHROPIC_API_KEY in .env."
            ) from error
        except anthropic.NotFoundError as error:
            raise LlmError(f"Unknown model or endpoint: {request.model}.") from error
        except anthropic.RateLimitError as error:
            raise LlmError(f"Rate limited after retries: {error.message}") from error
        except anthropic.APIStatusError as error:
            raise LlmError(f"Anthropic API error {error.status_code}: {error.message}") from error
        except anthropic.APIConnectionError as error:
            raise LlmError(f"Cannot reach the Anthropic API: {error}") from error
        return _to_result(message)


def _to_result(message: BetaMessage) -> BackendResult:
    usage = message.usage
    iterations = usage.iterations or []
    return BackendResult(
        text="".join(block.text for block in message.content if block.type == "text"),
        served_model=message.model,
        stop_reason=message.stop_reason,
        usage=Usage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            cache_write_tokens=usage.cache_creation_input_tokens or 0,
        ),
        request_id=message._request_id,  # pyright: ignore[reportPrivateUsage]
        refusal_category=message.stop_details.category if message.stop_details else None,
        fallback_used=any(entry.type == "fallback_message" for entry in iterations),
    )
