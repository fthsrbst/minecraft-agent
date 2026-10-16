"""Task-run records: one JSON line per attempt at a task, the unit the evaluation report counts.

A run links what was tried (task, arm, model, library snapshot) to where (seed, world instance,
visibility mode) and to the outcome (verdict, attempts, time, LLM calls and cost). The report is
computed from these files and the telemetry they point to via `trace_id` (AGENTS.md rules on
measurement and reproducibility).
"""

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agent_core.plugins import JsonObject, JsonValue
from agent_core.telemetry import JsonlWriter, new_trace_id, summarize_trace
from agent_core.verifier import Verdict


@dataclass(frozen=True, slots=True)
class TaskRunRecord:
    run_id: str
    task_id: str
    arm: str
    seed: int | None
    world_instance_id: str | None
    visibility: str | None
    models: Mapping[str, str]
    library_snapshot: str | None
    trace_id: str
    verdict: str
    attempts: int
    failure_reason: str | None
    started_at: str
    ended_at: str
    wall_time_s: float
    llm_calls: int
    llm_failed_calls: int
    llm_input_tokens: int
    llm_output_tokens: int
    llm_cost_usd: float
    llm_cost_complete: bool
    llm_cache_read_tokens: int
    llm_cache_write_tokens: int
    llm_telemetry_found: bool
    final_observation: JsonObject | None = None
    notes: JsonObject = field(default_factory=dict[str, JsonValue])


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class TaskRun:
    """An open run: start it before the first action, finish it once the verdict is known."""

    task_id: str
    arm: str
    seed: int | None = None
    world_instance_id: str | None = None
    visibility: str | None = None
    models: Mapping[str, str] = field(default_factory=dict[str, str])
    library_snapshot: str | None = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    # Pass this to every LLM call of the run so its cost can be summed.
    trace_id: str = field(default_factory=new_trace_id)
    started_at: str = field(default_factory=_now)
    _started: float = field(default_factory=time.monotonic)

    def finish(
        self,
        verdict: Verdict,
        *,
        telemetry_path: Path,
        attempts: int = 1,
        failure_reason: str | None = None,
        final_observation: JsonObject | None = None,
        notes: JsonObject | None = None,
    ) -> TaskRunRecord:
        totals = summarize_trace(telemetry_path, self.trace_id)
        return TaskRunRecord(
            run_id=self.run_id,
            task_id=self.task_id,
            arm=self.arm,
            seed=self.seed,
            world_instance_id=self.world_instance_id,
            visibility=self.visibility,
            models=dict(self.models),
            library_snapshot=self.library_snapshot,
            trace_id=self.trace_id,
            verdict=verdict.value,
            attempts=attempts,
            failure_reason=failure_reason,
            started_at=self.started_at,
            ended_at=_now(),
            wall_time_s=round(time.monotonic() - self._started, 3),
            llm_calls=totals.calls,
            llm_failed_calls=totals.failed_calls,
            llm_input_tokens=totals.input_tokens,
            llm_output_tokens=totals.output_tokens,
            llm_cost_usd=totals.cost_usd,
            llm_cost_complete=totals.cost_complete,
            llm_cache_read_tokens=totals.cache_read_tokens,
            llm_cache_write_tokens=totals.cache_write_tokens,
            llm_telemetry_found=totals.telemetry_found,
            final_observation=final_observation,
            notes=notes or {},
        )


class RunRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._writer = JsonlWriter(path)

    def record(self, record: TaskRunRecord) -> None:
        self._writer.write(record)
