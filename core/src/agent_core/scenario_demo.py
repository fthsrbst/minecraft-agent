"""P2.2 check: reset → predicate FALSE, setup → predicate TRUE, repeated to prove a scenario reruns.

    uv run --env-file ../.env python -m agent_core.scenario_demo ../plugins/<game> SCENARIO.json...

Needs the game server running and the plugin built. The bot process and the scenario process are
separate components: only the evaluator (this script) holds the scenario capability.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from agent_core.plugins import ManifestError, PluginClient, PluginError
from agent_core.scenarios import Scenario, ScenarioError, load_scenario, wait_for_verdict
from agent_core.verifier import Verdict


async def check_scenario(
    bot: PluginClient, scenario_plugin: PluginClient, player: str, scenario: Scenario, runs: int
) -> bool:
    passed = True
    for run in range(1, runs + 1):
        await scenario_plugin.request("scenario.reset", {"player": player})
        after_reset = await wait_for_verdict(bot, scenario.predicate, Verdict.FALSE)
        await scenario_plugin.request("scenario.setup", {"player": player, "spec": scenario.setup})
        after_setup = await wait_for_verdict(bot, scenario.predicate, Verdict.TRUE)
        ok = after_reset.verdict is Verdict.FALSE and after_setup.verdict is Verdict.TRUE
        passed &= ok
        print(
            f"{scenario.id} run {run}: after reset={after_reset.verdict} "
            f"({after_reset.waited_s}s), after setup={after_setup.verdict} "
            f"({after_setup.waited_s}s) -> {'PASS' if ok else 'FAIL'}"
        )
    return passed


async def run(plugin_dir: Path, scenario_paths: list[Path], runs: int) -> bool:
    scenarios = [load_scenario(path) for path in scenario_paths]
    async with (
        await PluginClient.start(plugin_dir) as bot,
        await PluginClient.start(plugin_dir, component="scenario") as scenario_plugin,
    ):
        hello = await bot.handshake()
        await scenario_plugin.handshake(timeout_s=15)
        # The bot reports its own name; the scenario targets that player.
        player = (await bot.observe()).get("username") or hello.get("username")
        if not isinstance(player, str):
            raise PluginError("The plugin did not report the bot's username.")
        results = [
            await check_scenario(bot, scenario_plugin, player, scenario, runs)
            for scenario in scenarios
        ]
        await scenario_plugin.request("scenario.reset", {"player": player})
        return all(results)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset/setup scenarios and check predicates.")
    parser.add_argument("plugin_dir", type=Path)
    parser.add_argument("scenarios", type=Path, nargs="+")
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args()
    try:
        passed = asyncio.run(run(args.plugin_dir, args.scenarios, args.runs))
    except (ManifestError, PluginError, ScenarioError, TimeoutError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("ALL PASS" if passed else "SOME FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
