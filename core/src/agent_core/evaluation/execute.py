"""One task run in a fresh world, recorded: shared by the evaluation runner and the demo.

    fresh world (seed) → connect the bot → reset/setup → Voyager loop → one task-run record
A run that breaks is recorded too (no survivorship bias, research.md §11.1).
"""

from dataclasses import dataclass
from pathlib import Path

from agent_core.library import SkillLibrary
from agent_core.llm import DEFAULT_MODELS, LlmClient, ModelRole
from agent_core.plugins import JsonObject, JsonValue, PluginClient, PluginError
from agent_core.runs import RunRecorder, TaskRun, TaskRunRecord
from agent_core.verifier import Verdict
from agent_core.voyager.loop import Attempt, PluginSession, VoyagerAgent
from agent_core.voyager.prompts import PROMPT_VERSION
from agent_core.voyager.task import Task


@dataclass(frozen=True, slots=True)
class RunPaths:
    records: Path
    telemetry: Path
    attempts_dir: Path


def _objects(value: JsonValue) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def attempt_note(run_id: str, attempt: Attempt, attempts_dir: Path) -> JsonObject:
    """One attempt for the record; its code goes to a file so records stay small."""
    code_file = None
    if attempt.code is not None:
        attempts_dir.mkdir(parents=True, exist_ok=True)
        path = attempts_dir / f"{run_id}-{attempt.number}.js"
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


async def execute_task(
    plugin_dir: Path,
    task: Task,
    *,
    arm: str,
    seed: int | None,
    library: SkillLibrary,
    learn: bool,
    attempts: int,
    llm: LlmClient,
    scenario: PluginClient,
    recorder: RunRecorder,
    paths: RunPaths,
    phase: str = "demo",
) -> TaskRunRecord:
    run = TaskRun(
        task_id=task.id,
        arm=arm,
        seed=seed,
        models={"code": DEFAULT_MODELS[ModelRole.CODE]},
        library_snapshot=library.snapshot_id(),
    )
    base_notes: JsonObject = {"phase": phase, "prompt_version": PROMPT_VERSION}
    try:
        if seed is not None:
            world = await scenario.request("scenario.world", {"seed": seed}, timeout_s=600)
            world_id = world.get("worldInstanceId") if isinstance(world, dict) else None
            run.world_instance_id = world_id if isinstance(world_id, str) else None
        async with await PluginClient.start(plugin_dir) as bot:
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
                max_attempts=attempts,
                learn=learn,
            )
            outcome = await agent.solve(task, session, trace_id=run.trace_id)
    except (PluginError, TimeoutError) as error:
        record = run.finish(
            Verdict.UNKNOWN,
            telemetry_path=paths.telemetry,
            attempts=0,
            failure_reason=f"{type(error).__name__}: {error}",
            notes={**base_notes, "broken": True},
        )
        recorder.record(record)
        return record

    record = run.finish(
        outcome.verdict,
        telemetry_path=paths.telemetry,
        attempts=len(outcome.attempts),
        failure_reason=outcome.reason,
        final_observation=outcome.final_observation,
        notes={
            **base_notes,
            "predicate": outcome.predicate,
            "predicate_source": outcome.predicate_source,
            # Runs that cannot count either way; left out of success rates.
            "invalid": outcome.invalid,
            "learned_skill": outcome.learned_skill,
            "used_skills": list(outcome.used_skills),
            "library_after": library.snapshot_id(),
            "attempts": [attempt_note(run.run_id, a, paths.attempts_dir) for a in outcome.attempts],
        },
    )
    recorder.record(record)
    return record
