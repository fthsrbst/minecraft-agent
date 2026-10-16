"""Acceptance predicates: JSON specs evaluated against a plugin observation.

Verification must be independent of the code being verified (AGENTS.md decision 6), so predicates
are plain data that a task carries before any skill code exists, and they are evaluated here, not
by the skill. Results are three-valued: when the observation cannot decide, the answer is UNKNOWN,
which never counts as success.

The predicates only assume the generic observation fields `inventory` (a list of
`{name, count}`) and `position` (`{x, y, z}`); item names are data from the task, not core code.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from agent_core.plugins.jsonrpc import JsonObject, JsonValue


class Verdict(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"

    def __bool__(self) -> bool:
        # Only TRUE is success; `if verdict:` must never treat UNKNOWN as passing.
        return self is Verdict.TRUE


class PredicateError(ValueError):
    """The predicate spec is malformed."""


type CompareOp = Literal["==", "!=", "<", "<=", ">", ">="]
COMPARE_OPS: tuple[CompareOp, ...] = ("==", "!=", "<", "<=", ">", ">=")


@dataclass(frozen=True, slots=True)
class HasItem:
    item: str
    count: int = 1


@dataclass(frozen=True, slots=True)
class Near:
    x: float
    y: float
    z: float
    radius: float


@dataclass(frozen=True, slots=True)
class Compare:
    path: str
    op: CompareOp
    value: float | str


@dataclass(frozen=True, slots=True)
class All:
    parts: tuple["Predicate", ...]


@dataclass(frozen=True, slots=True)
class AnyOf:
    parts: tuple["Predicate", ...]


@dataclass(frozen=True, slots=True)
class Not:
    part: "Predicate"


type Predicate = HasItem | Near | Compare | All | AnyOf | Not


# --- parsing -----------------------------------------------------------------------------------


def _number(spec: JsonObject, key: str, *, default: float | None = None) -> float:
    value = spec.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise PredicateError(f"`{key}` must be a finite number.")
    return float(value)


def _parts(spec: JsonObject) -> tuple[Predicate, ...]:
    parts = spec.get("of")
    if not isinstance(parts, list) or not parts:
        raise PredicateError("`of` must be a non-empty list of predicates.")
    return tuple(parse_predicate(part) for part in parts)


def parse_predicate(spec: JsonValue) -> Predicate:
    if not isinstance(spec, dict):
        raise PredicateError("A predicate must be a JSON object with a `type`.")
    kind = spec.get("type")
    match kind:
        case "has_item":
            item = spec.get("item")
            if not isinstance(item, str) or not item:
                raise PredicateError("has_item: `item` must be a non-empty string.")
            count = _number(spec, "count", default=1)
            if not count.is_integer() or count < 1:
                raise PredicateError("has_item: `count` must be a positive integer.")
            return HasItem(item, int(count))
        case "near":
            radius = _number(spec, "radius")
            if radius <= 0:
                raise PredicateError("near: `radius` must be positive.")
            return Near(_number(spec, "x"), _number(spec, "y"), _number(spec, "z"), radius)
        case "compare":
            path, op, value = spec.get("path"), spec.get("op"), spec.get("value")
            if not isinstance(path, str) or not path:
                raise PredicateError("compare: `path` must be a dotted field name.")
            if op not in COMPARE_OPS:
                raise PredicateError(f"compare: `op` must be one of {', '.join(COMPARE_OPS)}.")
            if isinstance(value, str):
                if op not in ("==", "!="):
                    raise PredicateError("compare: strings support only == and !=.")
                return Compare(path, op, value)
            return Compare(path, op, _number(spec, "value"))
        case "all":
            return All(_parts(spec))
        case "any":
            return AnyOf(_parts(spec))
        case "not":
            return Not(parse_predicate(spec.get("of")))
        case _:
            raise PredicateError(
                f"Unknown predicate type {kind!r}; known: has_item, near, compare, all, any, not."
            )


# --- evaluation --------------------------------------------------------------------------------


def _verdict(condition: bool) -> Verdict:
    return Verdict.TRUE if condition else Verdict.FALSE


def _lookup(observation: JsonObject, path: str) -> JsonValue | None:
    current: JsonValue = observation
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _real(value: JsonValue | None) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _item_count(observation: JsonObject, item: str) -> int | None:
    inventory = observation.get("inventory")
    if not isinstance(inventory, list):
        return None
    total = 0
    for stack in inventory:
        if not isinstance(stack, dict):
            return None
        name, count = stack.get("name"), _real(stack.get("count"))
        if not isinstance(name, str) or count is None:
            return None
        if name == item:
            total += int(count)
    return total


def _compare(left: float | str, op: CompareOp, right: float | str) -> bool:
    match op:
        case "==":
            return left == right
        case "!=":
            return left != right
        case _:
            assert isinstance(left, float) and isinstance(right, float)
            if op == "<":
                return left < right
            if op == "<=":
                return left <= right
            if op == ">":
                return left > right
            return left >= right


def _all(verdicts: Sequence[Verdict]) -> Verdict:
    # Kleene logic: one FALSE decides; otherwise any UNKNOWN keeps it undecided.
    if Verdict.FALSE in verdicts:
        return Verdict.FALSE
    return Verdict.UNKNOWN if Verdict.UNKNOWN in verdicts else Verdict.TRUE


def _any(verdicts: Sequence[Verdict]) -> Verdict:
    if Verdict.TRUE in verdicts:
        return Verdict.TRUE
    return Verdict.UNKNOWN if Verdict.UNKNOWN in verdicts else Verdict.FALSE


def evaluate(predicate: Predicate, observation: JsonObject) -> Verdict:
    match predicate:
        case HasItem(item, count):
            have = _item_count(observation, item)
            return Verdict.UNKNOWN if have is None else _verdict(have >= count)
        case Near(x, y, z, radius):
            position = observation.get("position")
            if not isinstance(position, dict):
                return Verdict.UNKNOWN
            coords = [_real(position.get(axis)) for axis in ("x", "y", "z")]
            if any(c is None for c in coords):
                return Verdict.UNKNOWN
            here = tuple(c for c in coords if c is not None)
            return _verdict(math.dist(here, (x, y, z)) <= radius)
        case Compare(path, op, expected):
            actual = _lookup(observation, path)
            if isinstance(expected, str):
                if not isinstance(actual, str):
                    return Verdict.UNKNOWN
                return _verdict(_compare(actual, op, expected))
            number = _real(actual)
            return Verdict.UNKNOWN if number is None else _verdict(_compare(number, op, expected))
        case All(parts):
            return _all([evaluate(part, observation) for part in parts])
        case AnyOf(parts):
            return _any([evaluate(part, observation) for part in parts])
        case Not(part):
            inner = evaluate(part, observation)
            if inner is Verdict.UNKNOWN:
                return Verdict.UNKNOWN
            return _verdict(inner is Verdict.FALSE)
