"""P2.1 live check: one cheap call through LlmClient, then print the telemetry record it wrote.

uv run --env-file ../.env python -m agent_core.llm_demo
"""

import asyncio
import sys
from pathlib import Path

from agent_core.llm import LlmClient, LlmError, ModelRole
from agent_core.llm.anthropic_backend import AnthropicBackend
from agent_core.telemetry import TelemetryRecorder

TELEMETRY_PATH = Path("runs/telemetry/llm-demo.jsonl")


async def run() -> None:
    telemetry = TelemetryRecorder(TELEMETRY_PATH)
    client = LlmClient(AnthropicBackend(), telemetry, timeout_s=60)
    response = await client.complete(
        "Name three things a new player of a survival sandbox game should do first. One line each.",
        role=ModelRole.TEXT,
        purpose="demo.hello",
        max_tokens=300,
    )
    print(response.text)
    cost = "unknown" if response.cost_usd is None else f"${response.cost_usd:.6f}"
    print(
        f"\nmodel={response.model} tokens in/out={response.usage.input_tokens}/"
        f"{response.usage.output_tokens} cost={cost} latency={response.latency_ms:.0f} ms"
    )


def main() -> int:
    try:
        asyncio.run(run())
    except LlmError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        # The record is written for failed calls too.
        if TELEMETRY_PATH.exists():
            print(f"\ntelemetry: {TELEMETRY_PATH.resolve()}")
            print(TELEMETRY_PATH.read_text(encoding="utf-8").splitlines()[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
