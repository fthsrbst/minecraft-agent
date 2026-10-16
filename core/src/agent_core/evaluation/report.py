"""The evaluation report (plan P4.2/P5.1): numbers computed only from the run records.

Per arm: success rate with a 95% Wilson interval, time, LLM calls and cost. Paired by (task,
seed): discordant pairs with an exact McNemar test, and time/calls/cost on pairs both arms solved.
Invalid runs (goal already true, no usable predicate) and broken runs are counted and listed,
never silently dropped (research.md §11.1).
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_core.evaluation.stats import mcnemar_exact, median, wilson

Record = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ArmSummary:
    arm: str
    runs: int
    valid: int
    successes: int
    invalid: int
    broken: int
    rate: float
    ci: tuple[float, float]
    median_seconds: float | None
    mean_llm_calls: float
    total_cost: float
    cost_per_success: float | None


def load_records(path: Path) -> list[Record]:
    if not path.exists():
        return []
    records: list[Record] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _invalid(record: Record) -> bool:
    return bool(record.get("notes", {}).get("invalid"))


def _broken(record: Record) -> bool:
    return bool(record.get("notes", {}).get("broken"))


def summarize(records: list[Record], arm: str) -> ArmSummary:
    mine = [r for r in records if r.get("arm") == arm]
    valid = [r for r in mine if not _invalid(r)]
    successes = sum(1 for r in valid if r.get("verdict") == "true")
    cost = sum(float(r.get("llm_cost_usd", 0.0)) for r in mine)
    return ArmSummary(
        arm=arm,
        runs=len(mine),
        valid=len(valid),
        successes=successes,
        invalid=len(mine) - len(valid),
        broken=sum(1 for r in mine if _broken(r)),
        rate=successes / len(valid) if valid else 0.0,
        ci=wilson(successes, len(valid)),
        median_seconds=median([float(r.get("wall_time_s", 0.0)) for r in valid]),
        mean_llm_calls=sum(int(r.get("llm_calls", 0)) for r in valid) / len(valid)
        if valid
        else 0.0,
        total_cost=round(cost, 4),
        cost_per_success=round(cost / successes, 4) if successes else None,
    )


@dataclass(frozen=True, slots=True)
class Paired:
    pairs: int
    both: int
    only_a: int
    only_b: int
    neither: int
    p_value: float
    time_ratio: float | None  # median of b/a wall time where both succeeded
    calls_a: float | None
    calls_b: float | None
    cost_a: float | None
    cost_b: float | None


def paired(records: list[Record], arm_a: str, arm_b: str) -> Paired:
    by_key: dict[tuple[str, int], dict[str, Record]] = defaultdict(dict)
    for record in records:
        if not _invalid(record):
            by_key[(record.get("task_id", ""), record.get("seed", 0))][record.get("arm", "")] = (
                record
            )
    both = only_a = only_b = neither = 0
    ratios: list[float] = []
    calls: dict[str, list[float]] = {arm_a: [], arm_b: []}
    costs: dict[str, list[float]] = {arm_a: [], arm_b: []}
    for runs in by_key.values():
        if arm_a not in runs or arm_b not in runs:
            continue
        a, b = runs[arm_a]["verdict"] == "true", runs[arm_b]["verdict"] == "true"
        if a and b:
            both += 1
            time_a = float(runs[arm_a].get("wall_time_s", 0.0))
            if time_a > 0:
                ratios.append(float(runs[arm_b].get("wall_time_s", 0.0)) / time_a)
            for arm in (arm_a, arm_b):
                calls[arm].append(float(runs[arm].get("llm_calls", 0)))
                costs[arm].append(float(runs[arm].get("llm_cost_usd", 0.0)))
        elif a:
            only_a += 1
        elif b:
            only_b += 1
        else:
            neither += 1
    return Paired(
        both + only_a + only_b + neither, both, only_a, only_b, neither,
        mcnemar_exact(only_a, only_b), median(ratios),
        median(calls[arm_a]), median(calls[arm_b]), median(costs[arm_a]), median(costs[arm_b]),
    )  # fmt: skip


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _ci(ci: tuple[float, float]) -> str:
    return f"{_pct(ci[0])} to {_pct(ci[1])}"


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _arm_row(s: ArmSummary) -> str:
    seconds = "" if s.median_seconds is None else f"{s.median_seconds:.0f} s"
    per_success = "" if s.cost_per_success is None else f"${s.cost_per_success:.3f}"
    return _row(
        [
            s.arm,
            str(s.valid),
            str(s.successes),
            f"{_pct(s.rate)} ({_ci(s.ci)})",
            seconds,
            f"{s.mean_llm_calls:.2f}",
            f"${s.total_cost:.2f}",
            per_success,
            str(s.invalid),
            str(s.broken),
        ]
    )


ARM_HEADER = [
    "Arm", "Valid runs", "Solved", "Rate (95% CI)", "Median time", "Mean LLM calls",
    "Cost", "$ per success", "Invalid", "Broken",
]  # fmt: skip


def build_report(out: Path) -> str:
    manifest: Record = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    learning = load_records(out / "learning.jsonl")
    test = load_records(out / "test.jsonl")
    arms: list[str] = [str(arm) for arm in manifest.get("test_arms", [])]
    raw = ", ".join(
        f"`{out / name}`" for name in ("learning.jsonl", "test.jsonl", "telemetry.jsonl")
    )
    lines = [
        f"# Evaluation report: plan {manifest.get('plan_id')}",
        "",
        f"- Commit `{manifest.get('git_commit')}`, prompt `{manifest.get('prompt_version')}`, "
        f"models {manifest.get('models')}",
        f"- Learning seeds {manifest.get('learning_seeds')}, "
        f"test seeds {manifest.get('test_seeds')}; "
        f"frozen library `{manifest.get('frozen_library')}`",
        f"- Raw data: {raw}",
        "",
        "## Learning phase",
        "",
    ]
    learned = [r for r in learning if r.get("notes", {}).get("learned_skill")]
    ls = summarize(learning, "voyager")
    lines += [
        f"{ls.successes}/{ls.valid} learning runs solved ({_pct(ls.rate)}, 95% CI {_ci(ls.ci)}); "
        f"{len(learned)} skills learned; cost ${ls.total_cost:.2f}.",
        "",
        "## Test phase (unseen seeds)",
        "",
        _row(ARM_HEADER),
        _row(["---"] * len(ARM_HEADER)),
    ]
    lines += [_arm_row(summarize(test, arm)) for arm in arms]
    if len(arms) >= 2:
        a, b = arms[0], arms[1]
        p = paired(test, a, b)
        lines += [
            "",
            f"## Paired: {a} vs {b} (same task, same seed)",
            "",
            f"- {p.pairs} pairs: both solved {p.both}, only {a} {p.only_a}, only {b} {p.only_b}, "
            f"neither {p.neither}; exact McNemar p = {p.p_value:.3f}.",
        ]
        if p.both and p.time_ratio is not None:
            lines.append(
                f"- On the {p.both} pairs both solved: median time {b}/{a} = {p.time_ratio:.2f}; "
                f"median LLM calls {p.calls_a} vs {p.calls_b}; "
                f"median cost ${p.cost_a or 0:.4f} vs ${p.cost_b or 0:.4f}."
            )
    lines += ["", "## Per task", "", _row(["Task", *arms]), _row(["---"] * (len(arms) + 1))]
    for task in sorted({str(r.get("task_id")) for r in test}):
        cells: list[str] = [task]
        for arm in arms:
            runs = [
                r
                for r in test
                if r.get("task_id") == task and r.get("arm") == arm and not _invalid(r)
            ]
            cells.append(f"{sum(r.get('verdict') == 'true' for r in runs)}/{len(runs)}")
        lines.append(_row(cells))
    return "\n".join(lines) + "\n"
