"""P2.4: the Voyager loop on task files, each in a fresh world; skills accumulate in a library.

    uv run --env-file ../.env python -m agent_core.voyager_demo ../plugins/<game> TASK.json...
        [--seed N] [--library runs/skills.sqlite] [--fresh-library] [--frozen | --no-library]
        [--attempts 3]

Arms: `voyager` (learns), `frozen-library` (uses the library, adds nothing), `no-library` (an
empty library that learns nothing: the baseline for the main claim).

Every task run is a record in runs/voyager.jsonl (arm, seed, world, library snapshot before and
after, predicate and who wrote it, verdict, attempts, LLM calls and cost); each attempt's code is
in runs/attempts/; LLM calls are in runs/telemetry/voyager.jsonl.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from agent_core.library import LibraryError, SkillLibrary
from agent_core.llm import DEFAULT_MODELS, LlmClient, LlmError, ModelRole
from agent_core.llm.anthropic_backend import AnthropicBackend
from agent_core.plugins import JsonObject, JsonValue, ManifestError, PluginClient, PluginError
from agent_core.runs import RunRecorder, TaskRun, TaskRunRecord
from agent_core.telemetry import TelemetryRecorder
from agent_core.verifier import Verdict
from agent_core.voyager.loop import Attempt, PluginSession, VoyagerAgent
from agent_core.voyager.prompts import PROMPT_VERSION
from agent_core.voyager.task import Task, TaskError, load_task

RUNS_PATH = Path("runs/voyager.jsonl")
TELEMETRY_PATH = Path("runs/telemetry/voyager.jsonl")
ATTEMPTS_DIR = Path("runs/attempts")
NO_LIBRARY_PATH = Path("runs/no-library.sqlite")


def _objects(value: JsonValue) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _arm(args: argparse.Namespace) -> str:
    if args.no_library:
        return "no-library"
    return "frozen-library" if args.frozen else "voyager"


def _attempt_note(run_id: str, attempt: Attempt) -> JsonObject:
    """One attempt for the record; its code goes to a file so records stay small."""
    code_file = None
    if attempt.code is not None:
        ATTEMPTS_DIR.mkdir(parents=True, exist_ok=True)
        path = ATTEMPTS_DIR / f"{run_id}-{attempt.number}.js"
        path.write_text(attempt.code, encoding="utf-8")
        code_file = str(path)
    return {
        "number": attempt.number,
        "skill": attempt.skill_name,
        "status": attempt.status,
        "verdict": attempt.verdict.value,
        "problem": attempt.problem,
        "seconds": attempt.duration_s,
        "used": list(attempt.used_skills),
        "clean_start": attempt.clean_start,
        "code_file": code_file,
    }


async def run_task(
    args: argparse.Namespace,
    task: Task,
    library: SkillLibrary,
    llm: LlmClient,
    scenario: PluginClient,
    recorder: RunRecorder,
) -> TaskRunRecord:
    arm = _arm(args)
    run = TaskRun(
        task_id=task.id,
        arm=arm,
        seed=args.seed,
        models={"code": DEFAULT_MODELS[ModelRole.CODE]},
        library_snapshot=library.snapshot_id(),
    )
    try:
        if args.seed is not None:
            world = await scenario.request("scenario.world", {"seed": args.seed}, timeout_s=600)
            world_id = world.get("worldInstanceId") if isinstance(world, dict) else None
            run.world_instance_id = world_id if isinstance(world_id, str) else None
        async with await PluginClient.start(args.plugin_dir) as bot:
            hello = await bot.handshake()
            visibility, guide = hello.get("visibility"), hello.get("skillGuide")
            run.visibility = visibility if isinstance(visibility, str) else None
            session = PluginSession(bot, scenario, task.reset, task.setup)
            await session.reset()
            agent = VoyagerAgent(
                llm,
                library,
                _objects(hello.get("skillApi")),
                guide if isinstance(guide, str) else "",
                max_attempts=args.attempts,
                learn=arm == "voyager",
            )
            outcome = await agent.solve(task, session, trace_id=run.trace_id)
    except (PluginError, TimeoutError) as error:
        # A broken run is still a run (no survivorship bias); the next task gets a fresh plugin.
        record = run.finish(
            Verdict.UNKNOWN,
            telemetry_path=TELEMETRY_PATH,
            attempts=0,
            failure_reason=f"{type(error).__name__}: {error}",
            notes={"prompt_version": PROMPT_VERSION},
        )
        recorder.record(record)
        return record

    record = run.finish(
        outcome.verdict,
        telemetry_path=TELEMETRY_PATH,
        attempts=len(outcome.attempts),
        failure_reason=outcome.reason,
        final_observation=outcome.final_observation,
        notes={
            "prompt_version": PROMPT_VERSION,
            "predicate": outcome.predicate,
            "predicate_source": outcome.predicate_source,
            # Runs that cannot count either way; left out of success rates.
            "invalid": outcome.invalid,
            "learned_skill": outcome.learned_skill,
            "used_skills": list(outcome.used_skills),
            "library_after": library.snapshot_id(),
            "attempts": [_attempt_note(run.run_id, attempt) for attempt in outcome.attempts],
        },
    )
    recorder.record(record)
    return record


async def run_all(args: argparse.Namespace) -> bool:
    tasks = [load_task(path) for path in args.tasks]
    if args.no_library:
        # A new, empty library per call: nothing to reuse, nothing kept.
        args.library = NO_LIBRARY_PATH
        args.library.unlink(missing_ok=True)
    elif args.fresh_library:
        args.library.unlink(missing_ok=True)
    library = SkillLibrary(args.library, read_only=args.frozen)
    llm = LlmClient(AnthropicBackend(), TelemetryRecorder(TELEMETRY_PATH), timeout_s=300)
    recorder = RunRecorder(RUNS_PATH)
    counted: list[bool] = []
    async with await PluginClient.start(args.plugin_dir, component="scenario") as scenario:
        await scenario.handshake(timeout_s=15)
        for task in tasks:
            record = await run_task(args, task, library, llm, scenario, recorder)
            notes = record.notes
            print(
                f"{task.id} [{record.arm}]: {record.verdict} after {record.attempts} attempt(s), "
                f"{record.wall_time_s:.0f} s, {record.llm_calls} LLM calls, "
                f"${record.llm_cost_usd:.4f}; learned={notes.get('learned_skill')}, "
                f"used={notes.get('used_skills')}, library {record.library_snapshot} -> "
                f"{notes.get('library_after')}"
                + (f"; invalid: {notes['invalid']}" if notes.get("invalid") else "")
                + (f"; reason: {record.failure_reason}" if record.failure_reason else "")
            )
            for attempt in _objects(notes.get("attempts")):
                print(f"  attempt: {attempt}")
            if notes.get("invalid") is None:
                counted.append(record.verdict == Verdict.TRUE.value)
    library.close()
    return bool(counted) and all(counted)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Voyager loop on tasks.")
    parser.add_argument("plugin_dir", type=Path)
    parser.add_argument("tasks", type=Path, nargs="+")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--library", type=Path, default=Path("runs/skills.sqlite"))
    parser.add_argument("--fresh-library", action="store_true")
    arms = parser.add_mutually_exclusive_group()
    arms.add_argument("--frozen", action="store_true", help="use the library, never add to it")
    arms.add_argument("--no-library", action="store_true", help="baseline: no skills to reuse")
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()
    try:
        passed = asyncio.run(run_all(args))
    except (ManifestError, PluginError, TaskError, LlmError, LibraryError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("ALL TASKS SOLVED" if passed else "SOME TASKS NOT SOLVED")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
