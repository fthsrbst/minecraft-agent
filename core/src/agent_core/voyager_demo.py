"""P2.4: the Voyager loop on task files, each in a fresh world; skills accumulate in a library.

    uv run --env-file ../.env python -m agent_core.voyager_demo ../plugins/<game> TASK.json...
        [--seed N] [--library runs/skills.sqlite] [--fresh-library] [--frozen] [--attempts 3]

Every task run is a record in runs/voyager.jsonl (arm, seed, world, library snapshot, verdict,
attempts, LLM calls and cost); LLM calls are in runs/telemetry/voyager.jsonl.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from agent_core.library import SkillLibrary
from agent_core.llm import DEFAULT_MODELS, LlmClient, LlmError, ModelRole
from agent_core.llm.anthropic_backend import AnthropicBackend
from agent_core.plugins import JsonObject, JsonValue, ManifestError, PluginClient, PluginError
from agent_core.runs import RunRecorder, TaskRun, TaskRunRecord
from agent_core.telemetry import TelemetryRecorder
from agent_core.verifier import Verdict
from agent_core.voyager.loop import PluginSession, TaskOutcome, VoyagerAgent
from agent_core.voyager.task import Task, TaskError, load_task

RUNS_PATH = Path("runs/voyager.jsonl")
TELEMETRY_PATH = Path("runs/telemetry/voyager.jsonl")


def _objects(value: JsonValue) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


async def run_task(
    args: argparse.Namespace,
    task: Task,
    library: SkillLibrary,
    llm: LlmClient,
    scenario: PluginClient,
    recorder: RunRecorder,
) -> TaskRunRecord:
    run = TaskRun(
        task_id=task.id,
        arm="frozen-library" if args.frozen else "voyager",
        seed=args.seed,
        models={"code": DEFAULT_MODELS[ModelRole.CODE]},
        library_snapshot=library.snapshot_id(),
    )
    outcome: TaskOutcome | None = None
    try:
        if args.seed is not None:
            world = await scenario.request("scenario.world", {"seed": args.seed}, timeout_s=600)
            world_id = world.get("worldInstanceId") if isinstance(world, dict) else None
            run.world_instance_id = world_id if isinstance(world_id, str) else None
        async with await PluginClient.start(args.plugin_dir) as bot:
            hello = await bot.handshake()
            visibility, guide = hello.get("visibility"), hello.get("skillGuide")
            run.visibility = visibility if isinstance(visibility, str) else None
            player = (await bot.observe({"nearby": False})).get("username")
            await scenario.request("scenario.reset", {**task.reset, "player": player})
            if task.setup:
                await scenario.request("scenario.setup", {"player": player, "spec": task.setup})
            agent = VoyagerAgent(
                llm,
                library,
                _objects(hello.get("skillApi")),
                guide if isinstance(guide, str) else "",
                max_attempts=args.attempts,
                learn=not args.frozen,
            )
            outcome = await agent.solve(task, PluginSession(bot), trace_id=run.trace_id)
    except BaseException as error:
        # A broken run is still a run (no survivorship bias in the results).
        recorder.record(
            run.finish(
                Verdict.UNKNOWN,
                telemetry_path=TELEMETRY_PATH,
                attempts=0,
                failure_reason=f"{type(error).__name__}: {error}",
            )
        )
        raise
    record = run.finish(
        outcome.verdict,
        telemetry_path=TELEMETRY_PATH,
        attempts=len(outcome.attempts),
        failure_reason=outcome.reason,
        notes={
            "learned_skill": outcome.learned_skill,
            "used_skills": list(outcome.used_skills),
            "attempts": [
                {
                    "skill": a.skill_name,
                    "status": a.status,
                    "verdict": a.verdict.value,
                    "problem": a.problem,
                    "seconds": a.duration_s,
                    "used": list(a.used_skills),
                }
                for a in outcome.attempts
            ],
        },
    )
    recorder.record(record)
    return record


async def run_all(args: argparse.Namespace) -> bool:
    tasks = [load_task(path) for path in args.tasks]
    if args.fresh_library:
        args.library.unlink(missing_ok=True)
    library = SkillLibrary(args.library, read_only=args.frozen)
    llm = LlmClient(AnthropicBackend(), TelemetryRecorder(TELEMETRY_PATH), timeout_s=300)
    recorder = RunRecorder(RUNS_PATH)
    results: list[bool] = []
    async with await PluginClient.start(args.plugin_dir, component="scenario") as scenario:
        await scenario.handshake(timeout_s=15)
        for task in tasks:
            record = await run_task(args, task, library, llm, scenario, recorder)
            notes = record.notes
            print(
                f"{task.id}: {record.verdict} after {record.attempts} attempt(s), "
                f"{record.wall_time_s:.0f} s, {record.llm_calls} LLM calls, "
                f"${record.llm_cost_usd:.4f}; learned={notes.get('learned_skill')}, "
                f"used={notes.get('used_skills')}, library before={record.library_snapshot}"
            )
            for attempt in _objects(notes.get("attempts")):
                print(f"  attempt: {attempt}")
            results.append(record.verdict == Verdict.TRUE.value)
    library.close()
    return all(results)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Voyager loop on tasks.")
    parser.add_argument("plugin_dir", type=Path)
    parser.add_argument("tasks", type=Path, nargs="+")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--library", type=Path, default=Path("runs/skills.sqlite"))
    parser.add_argument("--fresh-library", action="store_true")
    parser.add_argument("--frozen", action="store_true", help="use the library, never add to it")
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()
    try:
        passed = asyncio.run(run_all(args))
    except (ManifestError, PluginError, TaskError, LlmError, TimeoutError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("ALL TASKS SOLVED" if passed else "SOME TASKS NOT SOLVED")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
