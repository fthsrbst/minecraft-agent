import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from agent_core.plugins import (
    PROTOCOL_VERSION,
    PluginClient,
    PluginError,
    PluginExitedError,
    PluginRpcError,
)
from agent_core.plugins import client as client_module
from agent_core.plugins.jsonrpc import encode_request

FAKE_PLUGIN = Path(__file__).with_name("fake_plugin.py")


@pytest.fixture
def plugin_dir(tmp_path: Path) -> Path:
    manifest = {
        "id": "fake",
        "version": "0.0.1",
        "protocolVersion": PROTOCOL_VERSION,
        "command": [sys.executable, str(FAKE_PLUGIN)],
        "env": ["PLUGIN_ALLOWED"],
        "capabilities": [],
    }
    (tmp_path / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def run_with_plugin(plugin_dir: Path, scenario: Callable[[PluginClient], Awaitable[None]]) -> None:
    async def main() -> None:
        async with await PluginClient.start(plugin_dir) as plugin:
            await scenario(plugin)

    asyncio.run(main())


def test_handshake_observe_act_and_events(plugin_dir: Path) -> None:
    async def scenario(plugin: PluginClient) -> None:
        assert await plugin.handshake() == {"plugin": {"id": "fake"}}
        assert await plugin.next_event(timeout_s=2) == {"type": "ready"}
        assert await plugin.observe() == {"position": {"x": 1}}
        assert await plugin.act("chat", {"text": "hi"}) == {
            "echo": {"primitive": "chat", "args": {"text": "hi"}}
        }

    run_with_plugin(plugin_dir, scenario)


def test_rpc_error_carries_code_and_data(plugin_dir: Path) -> None:
    async def scenario(plugin: PluginClient) -> None:
        with pytest.raises(PluginRpcError) as caught:
            await plugin.request("fail")
        assert (caught.value.code, caught.value.rpc_message) == (-32001, "not ready")
        assert caught.value.data == {"retry": True}
        # The connection is still usable after an error.
        assert await plugin.observe() == {"position": {"x": 1}}

    run_with_plugin(plugin_dir, scenario)


def test_concurrent_requests_are_matched_by_id(plugin_dir: Path) -> None:
    async def scenario(plugin: PluginClient) -> None:
        results = await asyncio.gather(
            plugin.request("slow", {"seconds": 0.2}),
            plugin.act("move", {"direction": "left"}),
        )
        assert results[0] == "slow done"
        assert results[1] == {"echo": {"primitive": "move", "args": {"direction": "left"}}}

    run_with_plugin(plugin_dir, scenario)


def test_timeout_does_not_break_the_connection(plugin_dir: Path) -> None:
    async def scenario(plugin: PluginClient) -> None:
        with pytest.raises(TimeoutError, match=r"slow got no answer within 0\.1 s"):
            await plugin.request("slow", {"seconds": 0.3}, timeout_s=0.1)
        # The late answer to the timed-out request is ignored; the next request still works.
        assert await plugin.observe() == {"position": {"x": 1}}

    run_with_plugin(plugin_dir, scenario)


def test_crash_fails_pending_and_later_requests(plugin_dir: Path) -> None:
    async def scenario(plugin: PluginClient) -> None:
        with pytest.raises(PluginExitedError, match="code 3") as caught:
            await plugin.request("crash")
        assert "fatal: something broke" in str(caught.value)
        with pytest.raises(PluginExitedError):
            await plugin.observe()

    run_with_plugin(plugin_dir, scenario)


def test_close_stops_the_process(plugin_dir: Path) -> None:
    async def main() -> int | None:
        plugin = await PluginClient.start(plugin_dir)
        await plugin.observe()
        await plugin.close()
        return plugin.returncode

    assert asyncio.run(main()) == 0


def test_next_event_times_out_without_events(plugin_dir: Path) -> None:
    async def scenario(plugin: PluginClient) -> None:
        with pytest.raises(TimeoutError):
            await plugin.next_event(timeout_s=0.1)
        assert plugin.drain_events() == []

    run_with_plugin(plugin_dir, scenario)


# Regressions from the 2026-10-16 review.


def test_non_utf8_output_does_not_kill_the_reader(plugin_dir: Path) -> None:
    async def scenario(plugin: PluginClient) -> None:
        assert await plugin.request("garbage") == "after garbage"
        assert await plugin.observe() == {"position": {"x": 1}}

    run_with_plugin(plugin_dir, scenario)


def test_child_gets_only_base_and_listed_env(
    plugin_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLUGIN_ALLOWED", "yes")
    monkeypatch.setenv("SECRET_API_KEY", "must-not-leak")

    async def scenario(plugin: PluginClient) -> None:
        env = await plugin.request("env")
        assert isinstance(env, dict)
        assert env.get("PLUGIN_ALLOWED") == "yes"
        assert "SECRET_API_KEY" not in env

    run_with_plugin(plugin_dir, scenario)


def test_event_queue_is_bounded(plugin_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "MAX_QUEUED_EVENTS", 5)

    async def scenario(plugin: PluginClient) -> None:
        await plugin.request("spam_events", {"n": 20})
        assert [event["n"] for event in plugin.drain_events()] == [15, 16, 17, 18, 19]

    run_with_plugin(plugin_dir, scenario)


def test_boolean_id_does_not_answer_request_1(plugin_dir: Path) -> None:
    async def scenario(plugin: PluginClient) -> None:
        with pytest.raises(TimeoutError):
            await plugin.request("bool_id", timeout_s=0.3)

    run_with_plugin(plugin_dir, scenario)


def test_requests_after_close_fail_fast(plugin_dir: Path) -> None:
    async def main() -> None:
        plugin = await PluginClient.start(plugin_dir)
        await plugin.observe()
        await plugin.close()
        with pytest.raises(PluginError):
            await plugin.observe()

    asyncio.run(main())


def test_close_fails_requests_still_pending(plugin_dir: Path) -> None:
    async def main() -> None:
        plugin = await PluginClient.start(plugin_dir)
        slow = asyncio.create_task(plugin.request("slow", {"seconds": 5}, timeout_s=30))
        await asyncio.sleep(0.2)
        started = asyncio.get_running_loop().time()
        await plugin.close(timeout_s=0.5)
        with pytest.raises(PluginExitedError):
            await slow
        assert asyncio.get_running_loop().time() - started < 3

    asyncio.run(main())


def test_nan_is_refused_before_it_reaches_the_plugin() -> None:
    with pytest.raises(ValueError, match="JSON compliant"):
        encode_request(1, "skill.run", {"x": float("inf")})
