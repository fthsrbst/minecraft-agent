"""A pre-registered evaluation plan (research.md §11.1): tasks, learning seeds, test seeds, arms.

The plan file is frozen before the first test run; the runner copies it into the results so a
report can always be traced to exactly what was planned.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from agent_core.plugins import JsonValue
from agent_core.voyager.task import Task, load_task

ARMS = ("no-library", "frozen-library", "voyager")


class PlanError(ValueError):
    """The plan file is malformed."""


@dataclass(frozen=True, slots=True)
class Phase:
    seeds: tuple[int, ...]
    arms: tuple[str, ...]
    attempts: int


@dataclass(frozen=True, slots=True)
class EvalPlan:
    id: str
    description: str
    tasks: tuple[Task, ...]
    learning: Phase
    test: Phase
    source: Path


def _phase(data: JsonValue, name: str, default_arms: tuple[str, ...], source: Path) -> Phase:
    if not isinstance(data, dict):
        raise PlanError(f"{source}: `{name}` must be an object")
    seeds_value = data.get("seeds")
    arms_value = data.get("arms", list(default_arms))
    attempts = data.get("attempts", 3)
    seeds = [s for s in seeds_value if isinstance(s, int)] if isinstance(seeds_value, list) else []
    arms = [a for a in arms_value if isinstance(a, str)] if isinstance(arms_value, list) else []
    if not seeds or not isinstance(seeds_value, list) or len(seeds) != len(seeds_value):
        raise PlanError(f"{source}: `{name}.seeds` must be a non-empty list of integers")
    if not isinstance(arms_value, list) or not arms or len(arms) != len(arms_value):
        raise PlanError(f"{source}: `{name}.arms` must be a list from {', '.join(ARMS)}")
    if any(arm not in ARMS for arm in arms):
        raise PlanError(f"{source}: `{name}.arms` must be a list from {', '.join(ARMS)}")
    if not isinstance(attempts, int) or isinstance(attempts, bool) or not 1 <= attempts <= 6:
        raise PlanError(f"{source}: `{name}.attempts` must be 1 to 6")
    return Phase(tuple(seeds), tuple(arms), attempts)


def load_plan(path: Path) -> EvalPlan:
    try:
        data: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanError(f"{path}: cannot read plan ({error})") from error
    if not isinstance(data, dict):
        raise PlanError(f"{path}: a plan must be a JSON object")
    plan_id, description, pattern = data.get("id"), data.get("description", ""), data.get("tasks")
    if not isinstance(plan_id, str) or not plan_id.isidentifier():
        raise PlanError(f"{path}: `id` must be a simple name")
    if not isinstance(pattern, str):
        raise PlanError(f"{path}: `tasks` must be a glob relative to the plan")
    task_paths = sorted(path.parent.glob(pattern))
    if not task_paths:
        raise PlanError(f"{path}: no task files match {pattern}")
    learning = _phase(data.get("learning"), "learning", ("voyager",), path)
    test = _phase(data.get("test"), "test", ("no-library", "frozen-library"), path)
    if set(learning.seeds) & set(test.seeds):
        raise PlanError(f"{path}: learning and test seeds must differ (decision 14)")
    tasks = tuple(load_task(task_path) for task_path in task_paths)
    if len({task.id for task in tasks}) != len(tasks):
        raise PlanError(f"{path}: task ids must be unique")
    return EvalPlan(plan_id, str(description), tasks, learning, test, path)
