"""P3.4 check and value test (decision 10d): route example messages with each L1 provider.

    uv run --env-file ../.env python -m agent_core.decisions_demo ../plugins/<game>

Reads the plugin's command vocabulary and its labelled examples (commands/route-examples.json),
asks Jev and the keyword rule separately, and reports per message and overall: choice,
confidence, accepted, latency, and accuracy. Every call is logged to runs/telemetry/decisions.jsonl.
An L1 point that does not beat the rule stays in L0.
"""

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

from agent_core.commands import Vocabulary
from agent_core.decisions.client import ChoiceProvider, DecisionClient
from agent_core.decisions.questions import command_route
from agent_core.decisions.rules import KeywordRule
from agent_core.decisions.typesafe_provider import JevProvider
from agent_core.plugins import JsonValue

LOG_PATH = Path("runs/telemetry/decisions.jsonl")


async def run(plugin_dir: Path) -> None:
    vocabulary_data: JsonValue = json.loads(
        (plugin_dir / "commands" / "commands.json").read_text(encoding="utf-8")
    )
    examples_data: JsonValue = json.loads(
        (plugin_dir / "commands" / "route-examples.json").read_text(encoding="utf-8")
    )
    question = command_route(Vocabulary.from_handshake(vocabulary_data))
    raw = examples_data.get("examples") if isinstance(examples_data, dict) else None
    examples = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    jev = JevProvider()
    providers: dict[str, ChoiceProvider] = {"jev": jev, "rules": KeywordRule()}
    for name, provider in providers.items():
        client = DecisionClient([provider], LOG_PATH)
        correct = accepted = accepted_correct = 0
        latencies: list[float] = []
        print(f"\n== {name} ==")
        for example in examples:
            message, expected = str(example.get("message")), str(example.get("expected"))
            decision = await client.decide(question, {"message": message}, shadow=True)
            latencies.append(decision.latency_ms)
            hit = decision.choice == expected
            correct += hit
            accepted += decision.accepted
            accepted_correct += hit and decision.accepted
            mark = "ok " if hit else "BAD"
            print(
                f"  {mark} {message!r:42} -> {decision.choice!s:8} (want {expected:8}) "
                f"conf {decision.confidence:.2f} "
                f"{'accepted' if decision.accepted else 'escalate':8} "
                f"{decision.latency_ms:6.1f} ms"
            )
        total = len(latencies)
        print(
            f"  {name}: {correct}/{total} correct, {accepted} accepted "
            f"({accepted_correct} of them correct), "
            f"latency p50 {statistics.median(latencies):.0f} ms, "
            f"max {max(latencies):.0f} ms"
        )
    await jev.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Route example messages with each L1 provider.")
    parser.add_argument("plugin_dir", type=Path)
    asyncio.run(run(parser.parse_args().plugin_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
