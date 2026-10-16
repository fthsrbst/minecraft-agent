"""Scenarios: a reproducible start state plus the predicate that decides success.

The `setup` block is opaque to the core; the plugin's scenario component interprets it. Scenario
files therefore live with the plugin, and the core only loads and runs them.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

from agent_core.plugins import JsonObject, PluginClient
from agent_core.verifier import Predicate, PredicateError, Verdict, evaluate, parse_predicate


class ScenarioError(ValueError):
    """A scenario file is malformed."""


@dataclass(frozen=True, slots=True)
class Scenario:
    id: str
    description: str
    setup: JsonObject
    predicate: Predicate
    source: Path


def load_scenario(path: Path) -> Scenario:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ScenarioError(f"{path}: cannot read scenario ({error}).") from error
    if not isinstance(raw, dict):
        raise ScenarioError(f"{path}: a scenario must be a JSON object.")
    data: JsonObject = raw  # pyright: ignore[reportUnknownVariableType]
    scenario_id, description, setup = data.get("id"), data.get("description", ""), data.get("setup")
    if not isinstance(scenario_id, str) or not scenario_id:
        raise ScenarioError(f"{path}: `id` must be a non-empty string.")
    if not isinstance(description, str):
        raise ScenarioError(f"{path}: `description` must be a string.")
    if not isinstance(setup, dict):
        raise ScenarioError(f"{path}: `setup` must be an object.")
    try:
        predicate = parse_predicate(data.get("predicate"))
    except PredicateError as error:
        raise ScenarioError(f"{path}: invalid predicate: {error}") from error
    return Scenario(scenario_id, description, setup, predicate, path)


@dataclass(frozen=True, slots=True)
class Check:
    verdict: Verdict
    observation: JsonObject
    waited_s: float


async def wait_for_verdict(
    plugin: PluginClient,
    predicate: Predicate,
    expected: Verdict,
    *,
    within_s: float = 5.0,
    poll_s: float = 0.25,
) -> Check:
    """Observes until the predicate gives `expected` or time runs out; returns the last result.

    Server changes reach the bot's observation a few ticks later, so a single read right after a
    command can see the old state.
    """
    started = time.monotonic()
    while True:
        observation = await plugin.observe()
        verdict = evaluate(predicate, observation)
        waited = time.monotonic() - started
        if verdict is expected or waited >= within_s:
            return Check(verdict, observation, round(waited, 2))
        await asyncio.sleep(poll_s)
