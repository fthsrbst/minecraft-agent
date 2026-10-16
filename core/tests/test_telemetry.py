import json
from pathlib import Path

from agent_core.telemetry import LlmCallRecord, TelemetryRecorder, new_trace_id


def test_records_append_one_json_line_each(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "calls.jsonl"
    recorder = TelemetryRecorder(path)
    for purpose in ("a", "b"):
        recorder.record(
            LlmCallRecord(
                trace_id="t",
                purpose=purpose,
                provider="fake",
                requested_model="m",
                served_model="m",
                ok=True,
                latency_ms=1.5,
            )
        )
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["purpose"] for line in lines] == ["a", "b"]
    assert json.loads(lines[0])["cost_usd"] is None
    assert json.loads(lines[0])["timestamp"].endswith("+00:00")


def test_trace_ids_are_unique() -> None:
    assert len({new_trace_id() for _ in range(100)}) == 100
