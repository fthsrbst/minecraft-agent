"""Verification of a recorded skill (research.md §4.6 steps 7-8): replay it in fresh spots facing
different ways, check each result with the plugin's structure check (independent of the skill's
own report, decision 6), and keep the skill only if enough replays pass.

The evaluator owns the world here (decision 15): the scenario component prepares each spot and
gives the materials; the agent's bot only builds.
"""

import asyncio
import math
from dataclasses import dataclass
from pathlib import Path

from agent_core.library import SkillLibrary
from agent_core.plugins import JsonObject, JsonValue, PluginClient, PluginError
from agent_core.recording.skill import RecordedSkill
from agent_core.runs import RunRecorder, TaskRun
from agent_core.skills import run_skill
from agent_core.verifier import Verdict

REPLAY_TIMEOUT_S = 240.0
SETTLE_S = 2.0
# Decision 11c: in `full` the save decision comes from the verification score.
PASS_SHARE = 0.6


@dataclass(frozen=True, slots=True)
class Replay:
    index: int
    facing: str
    verdict: Verdict
    matched: int
    total: int
    skill_status: str
    error: str | None
    missing: tuple[JsonObject, ...]


@dataclass(frozen=True, slots=True)
class Verification:
    replays: tuple[Replay, ...]
    saved: bool

    @property
    def passed(self) -> int:
        return sum(r.verdict is Verdict.TRUE for r in self.replays)


def check_verdict(check: JsonObject) -> Verdict:
    """All cells match → TRUE; any wrong cell → FALSE; only unloaded cells missing → UNKNOWN."""
    total, matched, unknown = check.get("total"), check.get("matched"), check.get("unknown")
    if not (isinstance(total, int) and isinstance(matched, int) and isinstance(unknown, int)):
        return Verdict.UNKNOWN
    if total > 0 and matched == total:
        return Verdict.TRUE
    if matched + unknown < total:
        return Verdict.FALSE
    return Verdict.UNKNOWN


def _int(value: JsonValue) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _reply(value: JsonValue, method: str) -> JsonObject:
    if not isinstance(value, dict):
        raise PluginError(f"{method} answered with a non-object")
    return value


def _give(materials: dict[str, int]) -> list[JsonValue]:
    return [{"item": item, "count": count} for item, count in sorted(materials.items())]


async def replay_once(
    skill: RecordedSkill, bot: PluginClient, scenario: PluginClient, player: str, index: int
) -> Replay:
    arena = _reply(
        await scenario.request(
            "scenario.arena", {"player": player, "index": index, "give": _give(skill.materials)}
        ),
        "scenario.arena",
    )
    origin, facing = arena.get("origin"), arena.get("facing")
    if not isinstance(origin, dict) or not isinstance(facing, str):
        raise PluginError("scenario.arena answered without an origin and facing")
    await asyncio.sleep(SETTLE_S)  # the teleport and the new chunks reach the bot
    result = await run_skill(
        bot, skill.code, {"origin": origin, "facing": facing}, timeout_s=REPLAY_TIMEOUT_S
    )
    check = _reply(
        await bot.request(
            "record.check", {"blueprint": skill.blueprint, "origin": origin, "facing": facing}
        ),
        "record.check",
    )
    missing = check.get("missing")
    return Replay(
        index=index,
        facing=facing,
        verdict=check_verdict(check),
        matched=_int(check.get("matched")),
        total=_int(check.get("total")),
        skill_status=result.status,
        error=result.error,
        missing=tuple(m for m in missing if isinstance(m, dict))
        if isinstance(missing, list)
        else (),
    )


async def verify(
    skill: RecordedSkill,
    bot: PluginClient,
    scenario: PluginClient,
    *,
    runs: int,
    library: SkillLibrary | None,
    recorder: RunRecorder,
    telemetry_path: Path,
) -> Verification:
    observation = await bot.observe({"nearby": False})
    player, visibility = observation.get("username"), observation.get("visibility")
    if not isinstance(player, str):
        raise PluginError("the bot did not report its username")
    replays: list[Replay] = []
    for index in range(runs):
        run = TaskRun(
            task_id=f"recorded:{skill.card.name}",
            arm="replay",
            visibility=visibility if isinstance(visibility, str) else None,
        )
        replay = await replay_once(skill, bot, scenario, player, index)
        replays.append(replay)
        recorder.record(
            run.finish(
                replay.verdict,
                telemetry_path=telemetry_path,
                failure_reason=None
                if replay.verdict is Verdict.TRUE
                else f"{replay.matched}/{replay.total} cells; skill {replay.skill_status}: "
                f"{replay.error or ''}",
                notes={
                    "recording_id": skill.id,
                    "facing": replay.facing,
                    "index": index,
                    "missing": list(replay.missing),
                },
            )
        )
    passed = sum(r.verdict is Verdict.TRUE for r in replays)
    saved = False
    if library is not None and passed >= math.ceil(PASS_SHARE * runs):
        library.add(skill.card.name, skill.card.description, skill.code, f"demonstrated:{skill.id}")
        saved = True
    return Verification(tuple(replays), saved)
