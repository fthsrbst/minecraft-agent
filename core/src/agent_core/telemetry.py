"""Telemetry: every LLM or decision-model call becomes one JSON line.

AGENTS.md "Measurement is mandatory": the report computes cost and latency from these files, so a
record is written for failed calls too, and fields are never guessed: an unknown cost stays `null`.
"""

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from pathlib import Path


def new_trace_id() -> str:
    """A trace id groups every call made for one task, so a task's total cost can be summed."""
    return uuid.uuid4().hex


@dataclass(frozen=True, slots=True)
class LlmCallRecord:
    trace_id: str
    purpose: str
    provider: str
    requested_model: str
    served_model: str | None
    ok: bool
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None
    stop_reason: str | None = None
    fallback_used: bool = False
    request_id: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class JsonlWriter:
    """Appends one JSON object per line, flushed immediately, so a crash loses at most one line."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: object) -> None:
        data = asdict(record) if is_dataclass(record) and not isinstance(record, type) else record
        line = json.dumps(data, separators=(",", ":"), sort_keys=True)
        with self._lock, self.path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")


class TelemetryRecorder:
    """Writes one `LlmCallRecord` line per LLM call."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._writer = JsonlWriter(path)

    def record(self, record: LlmCallRecord) -> None:
        self._writer.write(record)


@dataclass(frozen=True, slots=True)
class TraceTotals:
    calls: int = 0
    failed_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    # False when at least one call had an unknown cost: the total is then a lower bound.
    cost_complete: bool = True
    latency_ms: float = 0.0


def summarize_trace(path: Path, trace_id: str) -> TraceTotals:
    """Sums the LLM calls of one trace (one task run) from a telemetry file."""
    if not path.exists():
        return TraceTotals()
    calls = failed = tokens_in = tokens_out = 0
    cost = latency = 0.0
    complete = True
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("trace_id") != trace_id:
            continue
        calls += 1
        failed += 0 if record.get("ok") else 1
        tokens_in += record.get("input_tokens", 0)
        tokens_out += record.get("output_tokens", 0)
        latency += record.get("latency_ms", 0.0)
        if record.get("cost_usd") is None:
            # A failed call before any response costs nothing; any other unknown cost is a gap.
            complete &= record.get("served_model") is None
        else:
            cost += record["cost_usd"]
    return TraceTotals(calls, failed, tokens_in, tokens_out, round(cost, 8), complete, latency)
