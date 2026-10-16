"""Runs one skill through a plugin: start it, wait for its `skill.done` event, never wait forever.

The plugin answers `skill.run` at once with a run id; the outcome arrives as an event because a
skill can run for minutes. If the core gives up first (timeout or task cancellation), it tells the
plugin to cancel, so no skill keeps acting after nobody listens (AGENTS.md decision 8).
"""

import asyncio
import contextlib
from dataclasses import dataclass

from agent_core.plugins import JsonObject, JsonValue, PluginClient, PluginError

# The plugin's own timeout ends the run; this margin covers the time to kill the executor and
# send the event. Only a broken plugin hits it.
DONE_EVENT_MARGIN_S = 15.0


class SkillRunError(PluginError):
    """The plugin did not report a usable outcome for a skill run."""


@dataclass(frozen=True, slots=True)
class SkillResult:
    run_id: str
    # ok | error | timeout | cancelled | crashed
    status: str
    result: JsonValue
    error: str | None
    duration_ms: float
    primitive_calls: int
    logs: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _parse_done(event: JsonObject) -> SkillResult:
    run_id, status = event.get("runId"), event.get("status")
    if not isinstance(run_id, str) or not isinstance(status, str):
        raise SkillRunError(f"malformed skill.done event: {event!r}")
    error = event.get("error")
    duration = event.get("durationMs")
    calls = event.get("primitiveCalls")
    logs = event.get("logs")
    return SkillResult(
        run_id=run_id,
        status=status,
        result=event.get("result"),
        error=error if isinstance(error, str) else None,
        duration_ms=float(duration) if isinstance(duration, int | float) else 0.0,
        primitive_calls=calls if isinstance(calls, int) else 0,
        logs=tuple(line for line in logs if isinstance(line, str))
        if isinstance(logs, list)
        else (),
    )


async def run_skill(
    plugin: PluginClient,
    code: str,
    args: JsonObject | None = None,
    *,
    timeout_s: float = 120.0,
) -> SkillResult:
    run_ids: list[str] = []
    # Every done event seen since registration, by run id. The reply and the done event can arrive
    # in one read, so the done event may be processed before this coroutine learns the run id;
    # recording it here means it is never lost, and a late event of an older run is never taken.
    seen: dict[str, JsonObject] = {}

    def is_done(event: JsonObject) -> bool:
        event_run = event.get("runId")
        if event.get("type") != "skill.done" or not isinstance(event_run, str):
            return False
        seen[event_run] = event
        return event_run in run_ids

    done = plugin.expect_event(is_done)
    run_id: str | None = None
    try:
        try:
            reply = await plugin.request(
                "skill.run",
                {"code": code, "args": args or {}, "timeoutMs": int(timeout_s * 1000)},
            )
        except (TimeoutError, asyncio.CancelledError):
            # The plugin may have started the run before the reply was lost: cancel whatever runs.
            await _cancel(plugin, None)
            raise
        found = reply.get("runId") if isinstance(reply, dict) else None
        if not isinstance(found, str):
            raise SkillRunError(f"skill.run returned no run id: {reply!r}")
        run_id = found
        run_ids.append(run_id)
        event = seen.get(run_id) or await done.wait(timeout_s + DONE_EVENT_MARGIN_S)
    except (TimeoutError, asyncio.CancelledError):
        if run_id is not None:
            await _cancel(plugin, run_id)
        raise
    finally:
        done.forget()
    return _parse_done(event)


async def _cancel(plugin: PluginClient, run_id: str | None) -> None:
    params: JsonObject = {} if run_id is None else {"runId": run_id}
    with contextlib.suppress(PluginError, TimeoutError):
        await plugin.request("skill.cancel", params, timeout_s=5)
