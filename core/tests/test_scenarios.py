import json
from pathlib import Path

import pytest

from agent_core.scenarios import ScenarioError, load_scenario
from agent_core.verifier import Verdict, evaluate


def write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


VALID = {
    "id": "has-things",
    "description": "holds two things",
    "setup": {"clear": True, "give": [{"item": "thing", "count": 2}]},
    "predicate": {"type": "has_item", "item": "thing", "count": 2},
}


def test_loads_a_scenario(tmp_path: Path) -> None:
    scenario = load_scenario(write(tmp_path, VALID))
    assert scenario.id == "has-things"
    assert scenario.setup == VALID["setup"]
    assert evaluate(scenario.predicate, {"inventory": []}) is Verdict.FALSE


def test_repository_scenarios_load() -> None:
    root = Path(__file__).resolve().parents[2] / "plugins"
    paths = sorted(root.glob("*/scenarios/*.json"))
    assert paths, "expected scenario files under plugins/*/scenarios/"
    for path in paths:
        load_scenario(path)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"id": ""}, "`id`"),
        ({"setup": []}, "`setup`"),
        ({"description": 3}, "`description`"),
        ({"predicate": {"type": "nope"}}, "invalid predicate"),
    ],
)
def test_rejects_bad_scenarios(tmp_path: Path, change: dict[str, object], message: str) -> None:
    with pytest.raises(ScenarioError, match=message):
        load_scenario(write(tmp_path, {**VALID, **change}))


def test_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError, match="cannot read"):
        load_scenario(tmp_path / "missing.json")
