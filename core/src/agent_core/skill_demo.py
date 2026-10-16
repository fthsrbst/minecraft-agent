"""P2.3 check: run a skill file through the plugin's executor and verify the result.

    uv run --env-file ../.env python -m agent_core.skill_demo ../plugins/<game> SKILL.js
        [--args JSON] [--predicate JSON] [--reset JSON] [--seed N] [--timeout S]

With `--seed` the run starts in a fresh world; with `--predicate` the player is reset first (the
predicate must be false), then the skill runs and the predicate decides. `--expect-status` checks
how the run ended instead (e.g. `timeout` for a skill that must be killed). One task-run record per
call is appended to runs/skill-demo.jsonl.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from agent_core.plugins import JsonObject, ManifestError, PluginClient, PluginError
from agent_core.runs import RunRecorder, TaskRun
from agent_core.scenarios import wait_for_verdict
from agent_core.skills import run_skill
from agent_core.verifier import PredicateError, Verdict, parse_predicate

RUNS_PATH = Path("runs/skill-demo.jsonl")
TELEMETRY_PATH = Path("runs/telemetry/skill-demo.jsonl")


def _json_object(text: str, name: str) -> JsonObject:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise SystemExit(f"--{name} must be a JSON object")
    return value  # pyright: ignore[reportUnknownVariableType]


async def run(args: argparse.Namespace, code: str) -> bool:
    predicate = (
        parse_predicate(_json_object(args.predicate, "predicate")) if args.predicate else None
    )
    async with await PluginClient.start(args.plugin_dir, component="scenario") as scenario:
        await scenario.handshake(timeout_s=15)
        world_id = None
        if args.seed is not None:
            world = await scenario.request("scenario.world", {"seed": args.seed}, timeout_s=600)
            world_id = world.get("worldInstanceId") if isinstance(world, dict) else None
        async with await PluginClient.start(args.plugin_dir) as bot:
            hello = await bot.handshake()
            visibility = hello.get("visibility")
            task = TaskRun(
                task_id=Path(args.skill).stem,
                arm="hand-written",
                seed=args.seed,
                world_instance_id=world_id if isinstance(world_id, str) else None,
                visibility=visibility if isinstance(visibility, str) else None,
            )
            player = (await bot.observe({"nearby": False})).get("username")
            if predicate is not None:
                reset = _json_object(args.reset, "reset") if args.reset else {}
                await scenario.request("scenario.reset", {**reset, "player": player})
                before = await wait_for_verdict(bot, predicate, Verdict.FALSE)
                print(f"before: predicate={before.verdict}")
            result = await run_skill(
                bot, code, _json_object(args.args, "args"), timeout_s=args.timeout
            )
            print(
                f"skill: status={result.status} in {result.duration_ms / 1000:.1f}s, "
                f"{result.primitive_calls} primitive calls, error={result.error}"
            )
            for line in result.logs:
                print(f"  log: {line}")
            print(f"  result: {json.dumps(result.result)}")
            # The bot must still answer after any skill outcome, including a killed executor.
            after = await bot.observe({"nearby": False})
            print(f"bot alive: health={after.get('health')} position={after.get('position')}")
            # A skill's own report is not verification (AGENTS.md decision 6): without a
            # predicate the verdict stays unknown.
            verdict = Verdict.UNKNOWN
            if predicate is not None:
                verdict = (await wait_for_verdict(bot, predicate, Verdict.TRUE, within_s=3)).verdict
                print(f"after: predicate={verdict}")
    RunRecorder(RUNS_PATH).record(
        task.finish(
            verdict,
            telemetry_path=TELEMETRY_PATH,
            failure_reason=None if result.ok else f"{result.status}: {result.error}",
            notes={"skill_status": result.status, "primitive_calls": result.primitive_calls},
        )
    )
    if args.expect_status is not None:
        return result.status == args.expect_status
    return verdict is Verdict.TRUE


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a skill file and verify it.")
    parser.add_argument("plugin_dir", type=Path)
    parser.add_argument("skill", type=Path)
    parser.add_argument("--args", default="{}")
    parser.add_argument("--predicate")
    parser.add_argument("--reset")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--expect-status", help="pass when the skill ends with this status (e.g. timeout)"
    )
    args = parser.parse_args()
    code = args.skill.read_text(encoding="utf-8")
    try:
        passed = asyncio.run(run(args, code))
    except (ManifestError, PluginError, PredicateError, TimeoutError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
