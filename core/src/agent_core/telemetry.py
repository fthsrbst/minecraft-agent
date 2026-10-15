"""Telemetry: every LLM or decision-model call becomes one JSON line.

AGENTS.md "Measurement is mandatory": the report computes cost and latency from these files, so a
record is written for failed calls too, and fields are never guessed: an unknown cost stays `null`.
"""

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
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


class TelemetryRecorder:
    """Appends records to a JSONL file; one line per call, flushed immediately."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, record: LlmCallRecord) -> None:
        line = json.dumps(asdict(record), separators=(",", ":"), sort_keys=True)
        with self._lock, self.path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")
