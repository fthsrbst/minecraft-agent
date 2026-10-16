import json
from pathlib import Path

import pytest

from agent_core.runs import RunRecorder, TaskRun
from agent_core.telemetry import LlmCallRecord, TelemetryRecorder, summarize_trace
from agent_core.verifier import Verdict


def call(
    trace: str, cost: float | None, *, ok: bool = True, served: str | None = "m"
) -> LlmCallRecord:
    return LlmCallRecord(
        trace_id=trace,
        purpose="test",
        provider="fake",
        requested_model="m",
        served_model=served,
        ok=ok,
        latency_ms=100.0,
        input_tokens=10,
        output_tokens=5,
        cost_usd=cost,
    )


def test_summarize_trace_sums_only_that_trace(tmp_path: Path) -> None:
    telemetry = TelemetryRecorder(tmp_path / "t.jsonl")
    telemetry.record(call("a", 0.01))
    telemetry.record(call("a", 0.02))
    telemetry.record(call("b", 5.0))
    totals = summarize_trace(telemetry.path, "a")
    assert (totals.calls, totals.input_tokens, totals.output_tokens) == (2, 20, 10)
    assert totals.cost_usd == pytest.approx(0.03)
    assert totals.cost_complete


def test_unknown_cost_marks_the_total_incomplete(tmp_path: Path) -> None:
    telemetry = TelemetryRecorder(tmp_path / "t.jsonl")
    telemetry.record(call("a", 0.01))
    telemetry.record(call("a", None))  # answered by a model with no price
    assert not summarize_trace(telemetry.path, "a").cost_complete


def test_a_call_that_failed_before_answering_costs_nothing(tmp_path: Path) -> None:
    telemetry = TelemetryRecorder(tmp_path / "t.jsonl")
    telemetry.record(call("a", None, ok=False, served=None))
    totals = summarize_trace(telemetry.path, "a")
    assert (totals.calls, totals.failed_calls, totals.cost_complete) == (1, 1, True)


def test_missing_telemetry_file_means_no_calls(tmp_path: Path) -> None:
    assert summarize_trace(tmp_path / "none.jsonl", "a").calls == 0


def test_task_run_record_links_task_world_outcome_and_cost(tmp_path: Path) -> None:
    telemetry = TelemetryRecorder(tmp_path / "t.jsonl")
    run = TaskRun(
        task_id="craft-pickaxe",
        arm="learned-library",
        seed=7,
        world_instance_id="seed7-abc",
        visibility="fair",
        models={"code": "m"},
        library_snapshot="lib-1",
    )
    telemetry.record(call(run.trace_id, 0.25))
    record = run.finish(
        Verdict.TRUE, telemetry_path=telemetry.path, attempts=2, final_observation={"tick": 5}
    )
    recorder = RunRecorder(tmp_path / "runs.jsonl")
    recorder.record(record)

    [line] = (tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    saved = json.loads(line)
    assert saved["task_id"] == "craft-pickaxe"
    assert saved["world_instance_id"] == "seed7-abc"
    assert saved["verdict"] == "true"
    assert saved["attempts"] == 2
    assert saved["llm_calls"] == 1
    assert saved["llm_cost_usd"] == pytest.approx(0.25)
    assert saved["wall_time_s"] >= 0
    assert saved["final_observation"] == {"tick": 5}


def test_a_cut_off_line_is_skipped_and_marks_the_total_incomplete(tmp_path: Path) -> None:
    telemetry = TelemetryRecorder(tmp_path / "t.jsonl")
    telemetry.record(call("a", 0.01))
    with telemetry.path.open("a", encoding="utf-8") as file:
        file.write('{"trace_id": "a", "cost_us')  # a crash mid-write
    totals = summarize_trace(telemetry.path, "a")
    assert (totals.calls, totals.unreadable_lines, totals.cost_complete) == (1, 1, False)


def test_a_missing_file_is_reported_as_missing(tmp_path: Path) -> None:
    assert not summarize_trace(tmp_path / "none.jsonl", "a").telemetry_found
