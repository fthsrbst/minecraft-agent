"""P2.2 check: reset → predicate FALSE, setup → predicate TRUE, repeated to prove a scenario reruns.

    uv run --env-file ../.env python -m agent_core.scenario_demo ../plugins/<game> SCENARIO.json...
        [--runs 2] [--seed N]

With `--seed`, every scenario run starts in a fresh copy of that seed's world. Each run is written
as a task-run record to runs/scenario-demo.jsonl (arm "scripted": setup does the work, no agent).

Needs the game server running and the plugin built. The bot process and the scenario process are
separate components: only the evaluator (this script) holds the scenario capability.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from agent_core.plugins import JsonObject, ManifestError, PluginClient, PluginError
from agent_core.runs import RunRecorder, TaskRun
from agent_core.scenarios import Scenario, ScenarioError, load_scenario, wait_for_verdict
from agent_core.verifier import Verdict

RUNS_PATH = Path("runs/scenario-demo.jsonl")
TELEMETRY_PATH = Path("runs/telemetry/scenario-demo.jsonl")


async def fresh_world(scenario_plugin: PluginClient, seed: int | None) -> str | None:
    if seed is None:
        return None
    world = await scenario_plugin.request("scenario.world", {"seed": seed}, timeout_s=600)
    world_id = world.get("worldInstanceId") if isinstance(world, dict) else None
    if not isinstance(world_id, str):
        raise PluginError(f"scenario.world returned no world id: {world!r}")
    return world_id


async def player_name(bot: PluginClient) -> str:
    player = (await bot.observe({"nearby": False})).get("username")
    if not isinstance(player, str):
        raise PluginError("The plugin did not report the bot's username.")
    return player


async def check_run(
    plugin_dir: Path,
    scenario_plugin: PluginClient,
    scenario: Scenario,
    seed: int | None,
    recorder: RunRecorder,
) -> bool:
    # A world switch restarts the server, so the bot connects after it, once per run.
    world_id = await fresh_world(scenario_plugin, seed)
    async with await PluginClient.start(plugin_dir) as bot:
        hello = await bot.handshake()
        visibility = hello.get("visibility")
        run = TaskRun(
            task_id=scenario.id,
            arm="scripted",
            seed=seed,
            world_instance_id=world_id,
            visibility=visibility if isinstance(visibility, str) else None,
        )
        player = await player_name(bot)
        await scenario_plugin.request("scenario.reset", {**scenario.reset, "player": player})
        after_reset = await wait_for_verdict(bot, scenario.predicate, Verdict.FALSE)
        await scenario_plugin.request("scenario.setup", {"player": player, "spec": scenario.setup})
        after_setup = await wait_for_verdict(bot, scenario.predicate, Verdict.TRUE)

    ok = after_reset.verdict is Verdict.FALSE and after_setup.verdict is Verdict.TRUE
    notes: JsonObject = {"after_reset": after_reset.verdict.value}
    failure = (
        None if ok else f"after reset={after_reset.verdict}, after setup={after_setup.verdict}"
    )
    recorder.record(
        run.finish(
            after_setup.verdict,
            telemetry_path=TELEMETRY_PATH,
            attempts=0,
            failure_reason=failure,
            notes=notes,
        )
    )
    print(
        f"{scenario.id} [{world_id or 'current world'}]: after reset={after_reset.verdict} "
        f"({after_reset.waited_s}s), after setup={after_setup.verdict} "
        f"({after_setup.waited_s}s) -> {'PASS' if ok else 'FAIL'}"
    )
    return ok


async def run_all(plugin_dir: Path, paths: list[Path], runs: int, seed: int | None) -> bool:
    scenarios = [load_scenario(path) for path in paths]
    recorder = RunRecorder(RUNS_PATH)
    async with await PluginClient.start(plugin_dir, component="scenario") as scenario_plugin:
        await scenario_plugin.handshake(timeout_s=15)
        results = [
            await check_run(plugin_dir, scenario_plugin, scenario, seed, recorder)
            for scenario in scenarios
            for _ in range(runs)
        ]
    return all(results)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset/setup scenarios and check predicates.")
    parser.add_argument("plugin_dir", type=Path)
    parser.add_argument("scenarios", type=Path, nargs="+")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--seed", type=int, default=None, help="fresh world of this seed per run")
    args = parser.parse_args()
    try:
        passed = asyncio.run(run_all(args.plugin_dir, args.scenarios, args.runs, args.seed))
    except (ManifestError, PluginError, ScenarioError, TimeoutError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"run records: {RUNS_PATH.resolve()}")
    print("ALL PASS" if passed else "SOME FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
