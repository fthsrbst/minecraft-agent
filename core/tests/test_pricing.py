import pytest

from agent_core.llm import Usage, cost_usd


def test_sonnet_cost_includes_cache_tokens() -> None:
    usage = Usage(
        input_tokens=10_000, output_tokens=2_000, cache_read_tokens=50_000, cache_write_tokens=4_000
    )
    # 10k*2 + 2k*10 + 50k*0.20 + 4k*2.50, per million
    assert cost_usd("claude-sonnet-5-5", usage) == pytest.approx(0.06)


def test_haiku_long_prompt_uses_the_higher_tier() -> None:
    short = Usage(input_tokens=100_000, output_tokens=1_000)
    long = Usage(input_tokens=100_001, output_tokens=1_000)
    assert cost_usd("claude-haiku-5-5", short) == pytest.approx(0.0105)
    assert cost_usd("claude-haiku-5-5", long) == pytest.approx(0.0525005)


def test_unknown_model_has_unknown_cost() -> None:
    assert cost_usd("some-future-model", Usage(input_tokens=1)) is None
