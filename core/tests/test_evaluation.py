import json
from pathlib import Path

import pytest

from agent_core.evaluation.plan import PlanError, load_plan
from agent_core.evaluation.report import build_report, paired, summarize
from agent_core.evaluation.stats import mcnemar_exact, median, wilson

REPO = Path(__file__).resolve().parents[2]


def test_wilson_matches_the_research_document() -> None:
    low, high = wilson(8, 10)
    assert (round(low, 2), round(high, 2)) == (0.49, 0.94)
    low, high = wilson(4, 5)
    assert (round(low, 2), round(high, 2)) == (0.38, 0.96)
    assert wilson(0, 0) == (0.0, 1.0)


def test_mcnemar_exact() -> None:
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(0, 6) == pytest.approx(2 / 64)
    assert mcnemar_exact(3, 3) == 1.0


def test_median() -> None:
    assert median([3.0, 1.0, 2.0]) == 2.0
    assert median([1.0, 2.0, 3.0, 4.0]) == 2.5
    assert median([]) is None


def test_the_shipped_plan_loads_and_keeps_seeds_apart() -> None:
    plan = load_plan(REPO / "plugins/minecraft/eval/plan-v1.json")
    assert len(plan.tasks) >= 20
    assert not set(plan.learning.seeds) & set(plan.test.seeds)
    assert plan.test.arms == ("no-library", "frozen-library")


def test_a_plan_with_shared_seeds_is_refused(tmp_path: Path) -> None:
    (tmp_path / "t.json").write_text(json.dumps({"id": "a", "goal": "x"}), encoding="utf-8")
    plan = {"id": "p", "tasks": "t.json", "learning": {"seeds": [1]}, "test": {"seeds": [1, 2]}}
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(PlanError, match="must differ"):
        load_plan(tmp_path / "plan.json")


def record(task: str, seed: int, arm: str, verdict: str, **extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "task_id": task, "seed": seed, "arm": arm, "verdict": verdict, "wall_time_s": 100.0,
        "llm_calls": 2, "llm_cost_usd": 0.02, "notes": {},
    }  # fmt: skip
    base.update(extra)
    return base


RECORDS = [
    record("a", 1, "no-library", "true", wall_time_s=100.0, llm_calls=2),
    record("a", 1, "frozen-library", "true", wall_time_s=50.0, llm_calls=1),
    record("b", 1, "no-library", "false"),
    record("b", 1, "frozen-library", "true"),
    record("c", 1, "no-library", "unknown", notes={"invalid": "already_true"}),
    record("c", 1, "frozen-library", "unknown", notes={"broken": True}),
]


def test_summaries_leave_invalid_runs_out_but_count_broken_ones() -> None:
    nolib = summarize(RECORDS, "no-library")
    assert (nolib.runs, nolib.valid, nolib.successes, nolib.invalid) == (3, 2, 1, 1)
    frozen = summarize(RECORDS, "frozen-library")
    assert (frozen.valid, frozen.successes, frozen.broken) == (3, 2, 1)


def test_paired_comparison() -> None:
    result = paired(RECORDS, "no-library", "frozen-library")
    assert (result.both, result.only_a, result.only_b) == (1, 0, 1)
    assert result.time_ratio == 0.5
    assert (result.calls_a, result.calls_b) == (2.0, 1.0)


def test_report_is_built_from_the_records(tmp_path: Path) -> None:
    manifest = {"plan_id": "v1", "test_arms": ["no-library", "frozen-library"], "test_seeds": [1]}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "test.jsonl").write_text(
        "\n".join(json.dumps(r) for r in RECORDS) + "\n", encoding="utf-8"
    )
    text = build_report(tmp_path)
    assert "| no-library | 2 | 1 | 50% (" in text
    assert "both solved 1, only no-library 0, only frozen-library 1" in text
    assert "| b | 0/1 | 1/1 |" in text
