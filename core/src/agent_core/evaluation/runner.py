"""Runs a pre-registered evaluation plan (plan P4.2, research.md §11.1).

    learning phase: arm `voyager` on the learning seeds, every task in order → a skill library
    freeze:         the learned library is copied and opened read-only from here on
    test phase:     on the test seeds, every task in every test arm, each in a fresh world
                    (`no-library`: a new empty library per run, learns nothing;
                     `frozen-library`: the frozen copy, learns nothing)

Results go to one directory: manifest.json (plan, commit, prompt version, models, frozen library
id), learning.jsonl and test.jsonl (task-run records), telemetry.jsonl, attempts/. A rerun with
`resume` skips (phase, task, seed, arm) combinations already recorded.
"""

import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from agent_core.evaluation.execute import RunPaths, execute_task
from agent_core.evaluation.plan import EvalPlan
from agent_core.library import SkillLibrary
from agent_core.llm import DEFAULT_MODELS, LlmClient
from agent_core.llm.anthropic_backend import AnthropicBackend
from agent_core.plugins import JsonObject, PluginClient
from agent_core.runs import RunRecorder
from agent_core.telemetry import TelemetryRecorder
from agent_core.voyager.prompts import PROMPT_VERSION
from agent_core.voyager.task import Task

LEARNED = "library-learned.sqlite"
FROZEN = "library-frozen.sqlite"


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _done(path: Path) -> set[tuple[str, int | None, str]]:
    keys: set[tuple[str, int | None, str]] = set()
    if not path.exists():
        return keys
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        keys.add((record.get("task_id"), record.get("seed"), record.get("arm")))
    return keys


def _write_manifest(out: Path, plan: EvalPlan, extra: JsonObject) -> None:
    path = out / "manifest.json"
    manifest: JsonObject = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    manifest.update(
        {
            "plan_id": plan.id,
            "plan_file": str(plan.source),
            "tasks": [task.id for task in plan.tasks],
            "learning_seeds": list(plan.learning.seeds),
            "test_seeds": list(plan.test.seeds),
            "test_arms": list(plan.test.arms),
            "prompt_version": PROMPT_VERSION,
            "models": {role.value: model for role, model in DEFAULT_MODELS.items()},
            "git_commit": _git_commit(),
            "python": sys.version.split()[0],
            **extra,
        }
    )
    manifest.setdefault("created_at", datetime.now(UTC).isoformat())
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _prepare(out: Path, plan: EvalPlan) -> None:
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(plan.source, out / "plan.json")
    _write_manifest(out, plan, {})


def _freeze(out: Path) -> Path:
    """Copies the learned library once; the test phase only ever opens the copy read-only."""
    frozen = out / FROZEN
    if not frozen.exists():
        learned = out / LEARNED
        if not learned.exists():
            raise FileNotFoundError("no learned library: run the learning phase first")
        shutil.copy(learned, frozen)
    return frozen


def _empty_library(out: Path) -> SkillLibrary:
    path = out / "library-empty.sqlite"
    path.unlink(missing_ok=True)
    return SkillLibrary(path)


async def run_plan(
    plan: EvalPlan,
    plugin_dir: Path,
    out: Path,
    *,
    phases: tuple[str, ...] = ("learning", "test"),
    tasks_limit: int | None = None,
) -> None:
    _prepare(out, plan)
    paths_for = {
        phase: RunPaths(out / f"{phase}.jsonl", out / "telemetry.jsonl", out / "attempts")
        for phase in ("learning", "test")
    }
    tasks: tuple[Task, ...] = plan.tasks[:tasks_limit] if tasks_limit else plan.tasks
    llm = LlmClient(AnthropicBackend(), TelemetryRecorder(out / "telemetry.jsonl"), timeout_s=300)

    async with await PluginClient.start(plugin_dir, component="scenario") as scenario:
        await scenario.handshake(timeout_s=15)

        if "learning" in phases:
            paths = paths_for["learning"]
            done = _done(paths.records)
            recorder = RunRecorder(paths.records)
            library = SkillLibrary(out / LEARNED)
            for seed in plan.learning.seeds:
                for task in tasks:
                    if (task.id, seed, "voyager") in done:
                        continue
                    record = await execute_task(
                        plugin_dir, task, arm="voyager", seed=seed, library=library, learn=True,
                        attempts=plan.learning.attempts, llm=llm, scenario=scenario,
                        recorder=recorder, paths=paths, phase="learning",
                    )  # fmt: skip
                    _progress("learning", record.task_id, seed, "voyager", record.verdict)
            library.close()

        if "test" in phases:
            # Freeze once: the test phase never sees a library that changes (decision 14).
            frozen = SkillLibrary(_freeze(out), read_only=True)
            _write_manifest(out, plan, {"frozen_library": frozen.snapshot_id()})
            paths = paths_for["test"]
            done = _done(paths.records)
            recorder = RunRecorder(paths.records)
            for seed in plan.test.seeds:
                for task in tasks:
                    for arm in plan.test.arms:
                        if (task.id, seed, arm) in done:
                            continue
                        if arm == "no-library":
                            library, learn = _empty_library(out), False
                        elif arm == "frozen-library":
                            library, learn = frozen, False
                        else:  # online learning on test seeds: a separate experiment
                            library, learn = SkillLibrary(out / "library-online.sqlite"), True
                        record = await execute_task(
                            plugin_dir, task, arm=arm, seed=seed, library=library, learn=learn,
                            attempts=plan.test.attempts, llm=llm, scenario=scenario,
                            recorder=recorder, paths=paths, phase="test",
                        )  # fmt: skip
                        _progress("test", record.task_id, seed, arm, record.verdict)
            frozen.close()


def _progress(phase: str, task: str, seed: int, arm: str, verdict: str) -> None:
    print(f"[{datetime.now(UTC).strftime('%H:%M:%S')}] {phase} {task} seed {seed} {arm}: {verdict}")
