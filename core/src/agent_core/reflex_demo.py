"""P3.1 check: a danger appears during a running skill; the L0 reflex must interrupt it and act.

    uv run --env-file ../.env python -m agent_core.reflex_demo ../plugins/<game> SKILL.js \\
        SCENARIO.json [--runs 3] [--delay 3] [--seed N]

Each run: reset → start the skill → after `delay` seconds apply the scenario's setup (e.g. a mob
next to the bot) → wait for the plugin's `reflex` event and the skill's end → the scenario's
predicate (e.g. still alive) decides. Reaction times are reported; one run record per run.
"""

import argparse
import asyncio
import statistics
import sys
from pathlib import Path

from agent_core.plugins import JsonObject, ManifestError, PluginClient, PluginError
from agent_core.runs import RunRecorder, TaskRun
from agent_core.scenarios import Scenario, ScenarioError, load_scenario, wait_for_verdict
from agent_core.skills import run_skill
from agent_core.verifier import Verdict

RUNS_PATH = Path("runs/reflex-demo.jsonl")
TELEMETRY_PATH = Path("runs/telemetry/reflex-demo.jsonl")
# A fight may take up to 30 s before the reflex event (sent at the end) arrives.
REFLEX_WAIT_S = 45.0
REACTION_TARGET_MS = 100.0


async def reflex_idle(bot: PluginClient, within_s: float = 30.0) -> None:
    """Waits until no reflex is busy (a fight from the previous run may still be ending)."""
    deadline = asyncio.get_running_loop().time() + within_s
    while asyncio.get_running_loop().time() < deadline:
        status = await bot.request("status")
        if not (isinstance(status, dict) and status.get("reflexBusy")):
            return
        await asyncio.sleep(0.5)
    raise TimeoutError("a reflex stayed busy for 30 s")


async def one_run(
    bot: PluginClient,
    scenario_plugin: PluginClient,
    scenario: Scenario,
    code: str,
    delay_s: float,
    run: TaskRun,
) -> tuple[bool, float | None, JsonObject]:
    player = (await bot.observe({"nearby": False})).get("username")
    await scenario_plugin.request("scenario.reset", {**scenario.reset, "player": player})
    await reflex_idle(bot)
    reflex = bot.expect_event(lambda event: event.get("type") == "reflex")
    skill = asyncio.create_task(run_skill(bot, code, {"seconds": 60}, timeout_s=90))
    try:
        await asyncio.sleep(delay_s)
        await scenario_plugin.request("scenario.setup", {"player": player, "spec": scenario.setup})
        event = await reflex.wait(REFLEX_WAIT_S)
        result = await skill
    finally:
        reflex.forget()
        if not skill.done():
            skill.cancel()
    alive = await wait_for_verdict(bot, scenario.predicate, Verdict.TRUE, within_s=2)
    reaction = event.get("reactionMs")
    reaction_ms = float(reaction) if isinstance(reaction, int | float) else None
    interrupted = result.status == "cancelled" and "reflex" in (result.error or "")
    ok = (
        alive.verdict is Verdict.TRUE
        and interrupted
        and reaction_ms is not None
        and reaction_ms <= REACTION_TARGET_MS
    )
    print(
        f"reflex={event.get('reflex')} target={event.get('target')} reaction={reaction_ms} ms "
        f"duration={event.get('durationMs')} ms outcome={event.get('outcome')!r}; "
        f"skill={result.status} ({result.error}); survived={alive.verdict} -> "
        f"{'PASS' if ok else 'FAIL'}"
    )
    notes: JsonObject = {"reflex_event": event, "skill_status": result.status}
    RunRecorder(RUNS_PATH).record(
        run.finish(
            alive.verdict if interrupted else Verdict.FALSE,
            telemetry_path=TELEMETRY_PATH,
            attempts=0,
            failure_reason=None if ok else "reflex did not interrupt the skill within the target",
            notes=notes,
        )
    )
    return ok, reaction_ms, event


async def run_all(args: argparse.Namespace) -> bool:
    scenario = load_scenario(args.scenario)
    code = args.skill.read_text(encoding="utf-8")
    passed: list[bool] = []
    reactions: list[float] = []
    async with await PluginClient.start(args.plugin_dir, component="scenario") as scenario_plugin:
        await scenario_plugin.handshake(timeout_s=15)
        world_id = None
        if args.seed is not None:
            world = await scenario_plugin.request(
                "scenario.world", {"seed": args.seed}, timeout_s=600
            )
            world_id = world.get("worldInstanceId") if isinstance(world, dict) else None
        async with await PluginClient.start(args.plugin_dir) as bot:
            hello = await bot.handshake()
            visibility = hello.get("visibility")
            player = (await bot.observe({"nearby": False})).get("username")
            for _ in range(args.runs):
                run = TaskRun(
                    task_id=scenario.id,
                    arm="reflex",
                    seed=args.seed,
                    world_instance_id=world_id if isinstance(world_id, str) else None,
                    visibility=visibility if isinstance(visibility, str) else None,
                )
                ok, reaction, _ = await one_run(
                    bot, scenario_plugin, scenario, code, args.delay, run
                )
                passed.append(ok)
                if reaction is not None:
                    reactions.append(reaction)
            # Leave no mobs behind for the next user of the server.
            await scenario_plugin.request("scenario.reset", {"player": player})
    if reactions:
        print(
            f"reaction: p50 {statistics.median(reactions):.1f} ms, max {max(reactions):.1f} ms "
            f"over {len(reactions)} runs (target <= {REACTION_TARGET_MS:.0f} ms)"
        )
    return all(passed)


def main() -> int:
    parser = argparse.ArgumentParser(description="Trigger the L0 reflex during a skill.")
    parser.add_argument("plugin_dir", type=Path)
    parser.add_argument("skill", type=Path)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--delay", type=float, default=3.0)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    try:
        passed = asyncio.run(run_all(args))
    except (ManifestError, PluginError, ScenarioError, TimeoutError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("ALL PASS" if passed else "SOME FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
