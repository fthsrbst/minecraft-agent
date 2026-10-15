import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from agent_core.plugins import (
    PROTOCOL_VERSION,
    PluginClient,
    PluginExitedError,
    PluginRpcError,
)

FAKE_PLUGIN = Path(__file__).with_name("fake_plugin.py")


@pytest.fixture
def plugin_dir(tmp_path: Path) -> Path:
    manifest = {
        "id": "fake",
        "version": "0.0.1",
        "protocolVersion": PROTOCOL_VERSION,
        "command": [sys.executable, str(FAKE_PLUGIN)],
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
