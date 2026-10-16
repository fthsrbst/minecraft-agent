"""Jev (TypeSafe System One) as a `ChoiceProvider` (decision 10)."""

from typesafe_sdk import AsyncTypeSafeClient, Choice, RetryPolicy, TypeSafeError

from agent_core.decisions.client import ChoiceQuestion, DecisionError, ProviderAnswer
from agent_core.plugins import JsonObject

DEFAULT_MODEL = "jev-latest"

__all__ = ["DEFAULT_MODEL", "JevProvider", "TypeSafeError"]


class JevProvider:
    name = "jev"

    def __init__(
        self, client: AsyncTypeSafeClient | None = None, *, timeout_s: float = 2.0
    ) -> None:
        # Reads TYPESAFE_API_KEY from the environment; one fast retry, then the caller falls back.
        self._client = client or AsyncTypeSafeClient(
            model=DEFAULT_MODEL,
            retry=RetryPolicy(max_retries=1, backoff_max=0.2, timeout=timeout_s),
        )

    async def choose(self, question: ChoiceQuestion, state: JsonObject) -> ProviderAnswer:
        try:
            # The SDK's recursive JSON type is partly unknown to pyright; the call itself is typed.
            response = await self._client.system_one(  # pyright: ignore[reportUnknownMemberType]
                state=state,
                questions={
                    question.id: Choice(
                        instructions=question.instructions,
                        criteria=dict(question.options),
                    )
                },
            )
        except TypeSafeError as error:
            raise DecisionError(f"TypeSafe: {error}") from error
        answer = response.choices.get(question.id)
        if answer is None:
            raise DecisionError("TypeSafe returned no answer for the question")
        return ProviderAnswer(
            answer.choice, dict(answer.probabilities), float(answer.confidence), response.model
        )

    async def close(self) -> None:
        await self._client.aclose()
