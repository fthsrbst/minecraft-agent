"""Predicates must never report success on a negative state (P2.2 acceptance)."""

import math

import pytest

from agent_core.plugins.jsonrpc import JsonObject, JsonValue
from agent_core.verifier import PredicateError, Verdict, evaluate, parse_predicate

T, F, U = Verdict.TRUE, Verdict.FALSE, Verdict.UNKNOWN

STATE: JsonObject = {
    "position": {"x": 10.0, "y": 64.0, "z": -3.0},
    "health": 18,
    "dimension": "overworld",
    "inventory": [
        {"name": "log", "count": 2},
        {"name": "log", "count": 1},
        {"name": "apple", "count": 5},
    ],
}


def check(spec: JsonValue, observation: JsonObject = STATE) -> Verdict:
    return evaluate(parse_predicate(spec), observation)


HAS_3_LOGS: JsonObject = {"type": "has_item", "item": "log", "count": 3}


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (HAS_3_LOGS, T),  # counts are summed across stacks
        ({"type": "has_item", "item": "log", "count": 4}, F),
        ({"type": "has_item", "item": "stone"}, F),
        ({"type": "near", "x": 11, "y": 64, "z": -3, "radius": 1}, T),
        ({"type": "near", "x": 12, "y": 64, "z": -3, "radius": 1.5}, F),
        ({"type": "compare", "path": "health", "op": ">=", "value": 18}, T),
        ({"type": "compare", "path": "health", "op": ">", "value": 18}, F),
        ({"type": "compare", "path": "position.y", "op": "<", "value": 70}, T),
        ({"type": "compare", "path": "dimension", "op": "==", "value": "overworld"}, T),
        ({"type": "compare", "path": "dimension", "op": "!=", "value": "overworld"}, F),
    ],
)
def test_leaf_predicates(spec: JsonObject, expected: Verdict) -> None:
    assert check(spec) is expected


@pytest.mark.parametrize(
    "negative",
    [
        {},  # nothing observed
        {"inventory": "3 logs"},  # wrong shape
        {"inventory": [{"name": "log"}]},  # count missing
        {"inventory": [{"name": "log", "count": True}]},  # a boolean is not a count
        {"inventory": [{"name": "log", "count": 3}, "junk"]},  # one bad stack spoils the list
    ],
)
def test_malformed_observations_are_unknown_not_success(negative: JsonObject) -> None:
    assert check(HAS_3_LOGS, negative) is U


@pytest.mark.parametrize(
    ("observation", "spec"),
    [
        ({"position": {"x": 1, "y": 2}}, {"type": "near", "x": 1, "y": 2, "z": 0, "radius": 5}),
        ({}, {"type": "compare", "path": "health", "op": ">=", "value": 1}),
        ({"health": "full"}, {"type": "compare", "path": "health", "op": ">=", "value": 1}),
        ({"dimension": 0}, {"type": "compare", "path": "dimension", "op": "==", "value": "end"}),
    ],
)
def test_missing_or_mistyped_fields_are_unknown(observation: JsonObject, spec: JsonObject) -> None:
    assert check(spec, observation) is U


UNKNOWN_SPEC: JsonObject = {"type": "compare", "path": "missing", "op": "==", "value": 1}
TRUE_SPEC: JsonObject = {"type": "has_item", "item": "apple"}
FALSE_SPEC: JsonObject = {"type": "has_item", "item": "stone"}


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ({"type": "all", "of": [TRUE_SPEC, TRUE_SPEC]}, T),
        ({"type": "all", "of": [TRUE_SPEC, UNKNOWN_SPEC]}, U),
        ({"type": "all", "of": [FALSE_SPEC, UNKNOWN_SPEC]}, F),
        ({"type": "any", "of": [FALSE_SPEC, UNKNOWN_SPEC]}, U),
        ({"type": "any", "of": [TRUE_SPEC, UNKNOWN_SPEC]}, T),
        ({"type": "any", "of": [FALSE_SPEC, FALSE_SPEC]}, F),
        ({"type": "not", "of": FALSE_SPEC}, T),
        ({"type": "not", "of": TRUE_SPEC}, F),
        ({"type": "not", "of": UNKNOWN_SPEC}, U),  # negating ignorance is still ignorance
    ],
)
def test_three_valued_logic(spec: JsonObject, expected: Verdict) -> None:
    assert check(spec) is expected


def test_only_true_is_truthy() -> None:
    assert bool(T)
    assert not bool(F)
    assert not bool(U)


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ("has_item", "JSON object"),
        ({"type": "teleported"}, "Unknown predicate type"),
        ({"type": "has_item"}, "`item`"),
        ({"type": "has_item", "item": "log", "count": 0}, "positive integer"),
        ({"type": "has_item", "item": "log", "count": 1.5}, "positive integer"),
        ({"type": "near", "x": 0, "y": 0, "z": 0, "radius": 0}, "radius"),
        ({"type": "near", "x": True, "y": 0, "z": 0, "radius": 1}, "`x`"),
        ({"type": "compare", "path": "health", "op": "~", "value": 1}, "`op`"),
        ({"type": "compare", "path": "dimension", "op": "<", "value": "end"}, "only == and !="),
        ({"type": "all", "of": []}, "non-empty"),
    ],
)
def test_malformed_specs_are_rejected(spec: JsonValue, message: str) -> None:
    with pytest.raises(PredicateError, match=message):
        parse_predicate(spec)


# Regressions from the 2026-10-16 review: non-finite numbers made `not`/`!=` report TRUE.
NAN_STATE: JsonObject = {"position": {"x": math.nan, "y": 64.0, "z": 0.0}, "health": math.inf}


@pytest.mark.parametrize(
    "spec",
    [
        {"type": "not", "of": {"type": "near", "x": 0, "y": 64, "z": 0, "radius": 1}},
        {"type": "near", "x": 0, "y": 64, "z": 0, "radius": 1},
        {"type": "compare", "path": "health", "op": "!=", "value": 20},
        {"type": "not", "of": {"type": "compare", "path": "health", "op": "<", "value": 20}},
    ],
)
def test_non_finite_numbers_are_unknown(spec: JsonObject) -> None:
    assert check(spec, NAN_STATE) is U


@pytest.mark.parametrize("count", [-5, 1.5, math.nan])
def test_impossible_stack_counts_are_unknown(count: float) -> None:
    observation: JsonObject = {
        "inventory": [{"name": "log", "count": count}, {"name": "log", "count": 6}]
    }
    assert check({"type": "has_item", "item": "log"}, observation) is U


NEAR_ORIGIN_OVERWORLD: JsonObject = {
    "type": "near",
    "x": 0,
    "y": 64,
    "z": 0,
    "radius": 2,
    "dimension": "overworld",
}


@pytest.mark.parametrize(
    ("dimension", "expected"),
    [("overworld", T), ("the_nether", F), (None, U)],
)
def test_near_checks_the_dimension(dimension: str | None, expected: Verdict) -> None:
    observation: JsonObject = {"position": {"x": 0, "y": 64, "z": 0}}
    if dimension is not None:
        observation["dimension"] = dimension
    assert check(NEAR_ORIGIN_OVERWORLD, observation) is expected
