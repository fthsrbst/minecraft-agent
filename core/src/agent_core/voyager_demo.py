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

from agent_core.evaluation.execute import RunPaths, execute_task
from agent_core.library import LibraryError, SkillLibrary
from agent_core.llm import LlmClient, LlmError
from agent_core.llm.anthropic_backend import AnthropicBackend
from agent_core.plugins import JsonObject, JsonValue, ManifestError, PluginClient, PluginError
from agent_core.runs import RunRecorder, TaskRunRecord
from agent_core.telemetry import TelemetryRecorder
from agent_core.verifier import Verdict
from agent_core.voyager.task import Task, TaskError, load_task

RUNS_PATH = Path("runs/voyager.jsonl")
TELEMETRY_PATH = Path("runs/telemetry/voyager.jsonl")
ATTEMPTS_DIR = Path("runs/attempts")
NO_LIBRARY_PATH = Path("runs/no-library.sqlite")


def _arm(args: argparse.Namespace) -> str:
    if args.no_library:
        return "no-library"
    return "frozen-library" if args.frozen else "voyager"


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
    arm = _arm(args)
    return await execute_task(
        args.plugin_dir,
        task,
        arm=arm,
        seed=args.seed,
        library=library,
        learn=arm == "voyager",
        attempts=args.attempts,
        llm=llm,
        scenario=scenario,
        recorder=recorder,
        paths=RunPaths(RUNS_PATH, TELEMETRY_PATH, ATTEMPTS_DIR),
    )


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
