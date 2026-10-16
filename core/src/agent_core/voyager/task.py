"""A learning task: a goal in words, how to judge it, and how to set the world up for it.

Task files live with the plugin (they name game things); the core treats `setup` and `reset` as
opaque and only needs the goal text and, ideally, an acceptance predicate.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from agent_core.plugins import JsonObject, JsonValue
from agent_core.verifier import Predicate, PredicateError, parse_predicate

DEFAULT_TIMEOUT_S = 180.0


class TaskError(ValueError):
    """A task file is malformed."""


@dataclass(frozen=True, slots=True)
class Task:
    id: str
    goal: str
    # None: the loop asks the LLM to write one before any code (predicate-first, decision 6).
    predicate: Predicate | None = None
    setup: JsonObject = field(default_factory=dict[str, JsonValue])
    reset: JsonObject = field(default_factory=dict[str, JsonValue])
    timeout_s: float = DEFAULT_TIMEOUT_S
    # The predicate as written in the task file; the prompt shows this JSON.
    predicate_spec: JsonValue = None


def load_task(path: Path) -> Task:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TaskError(f"{path}: cannot read task ({error}).") from error
    if not isinstance(raw, dict):
        raise TaskError(f"{path}: a task must be a JSON object.")
    data: JsonObject = raw  # pyright: ignore[reportUnknownVariableType]
    task_id, goal = data.get("id"), data.get("goal")
    if not isinstance(task_id, str) or not task_id:
        raise TaskError(f"{path}: `id` must be a non-empty string.")
    if not isinstance(goal, str) or not goal.strip():
        raise TaskError(f"{path}: `goal` must be a non-empty string.")
    setup, reset = data.get("setup", {}), data.get("reset", {})
    if not isinstance(setup, dict) or not isinstance(reset, dict):
        raise TaskError(f"{path}: `setup` and `reset` must be objects.")
    timeout = data.get("timeoutS", DEFAULT_TIMEOUT_S)
    if isinstance(timeout, bool) or not isinstance(timeout, int | float) or not 1 <= timeout <= 600:
        raise TaskError(f"{path}: `timeoutS` must be a number from 1 to 600.")
    predicate = None
    spec = data.get("predicate")
    if "predicate" in data:
        try:
            predicate = parse_predicate(data["predicate"])
        except PredicateError as error:
            raise TaskError(f"{path}: invalid predicate: {error}") from error
    return Task(task_id, goal.strip(), predicate, setup, reset, float(timeout), spec)
