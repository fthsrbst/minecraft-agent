"""USD prices per million tokens (Anthropic first-party API, checked 2026-10-15).

Update this table when prices change; `cost_usd` returns None for an unknown model rather than a
wrong number, so a missing row shows up as a gap in the report instead of a silent zero.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Price:
    input: float
    output: float
    cache_read: float
    # 5-minute cache writes cost 1.25x the input price.
    cache_write: float


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_read=0.20, cache_write=5.00),
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_read=0.20, cache_write=2.50),
    # Haiku 5.5 cache prices are not published separately; assumed at the usual 0.1x / 1.25x.
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125),
}

# Haiku 5.5 charges more for long prompts (over 100K tokens).
LONG_PROMPT_THRESHOLD = 100_000
LONG_PROMPT_PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price(input=0.50, output=2.50, cache_read=0.05, cache_write=0.625),
}


def cost_usd(model: str, usage: Usage) -> float | None:
    price = PRICES.get(model)
    if price is None:
        return None
    if usage.prompt_tokens > LONG_PROMPT_THRESHOLD:
        price = LONG_PROMPT_PRICES.get(model, price)
    total = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + usage.cache_write_tokens * price.cache_write
    ) / 1_000_000
    return round(total, 8)
