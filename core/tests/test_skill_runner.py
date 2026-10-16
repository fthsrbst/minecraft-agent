import asyncio
import json
import sys
from pathlib import Path

import pytest

from agent_core.plugins import PROTOCOL_VERSION, PluginClient
from agent_core.skills import run_skill
from agent_core.skills import runner as runner_module

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


def test_done_event_in_the_same_read_as_the_reply_is_not_lost(plugin_dir: Path) -> None:
    # The fake plugin writes the reply and the done event back to back.
    async def main() -> None:
        async with await PluginClient.start(plugin_dir) as plugin:
            result = await run_skill(plugin, "ok", {"n": 1}, timeout_s=5)
            assert result.ok
            assert result.result == {"args": {"n": 1}}
            assert (result.primitive_calls, result.logs) == (3, ("started", "finished"))

    asyncio.run(main())


def test_failed_skill_reports_error(plugin_dir: Path) -> None:
    async def main() -> None:
        async with await PluginClient.start(plugin_dir) as plugin:
            result = await run_skill(plugin, "fail", timeout_s=5)
            assert (result.status, result.error, result.ok) == ("error", "boom", False)

    asyncio.run(main())


def test_core_timeout_cancels_the_run_in_the_plugin(
    plugin_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(runner_module, "DONE_EVENT_MARGIN_S", 0.2)

    async def main() -> None:
        async with await PluginClient.start(plugin_dir) as plugin:
            with pytest.raises(TimeoutError):
                await run_skill(plugin, "hang", timeout_s=0.1)
            # The plugin logs the cancel on stderr; give the reader a moment.
            await asyncio.sleep(0.2)

    with caplog.at_level("INFO"):
        asyncio.run(main())
    assert any("cancelled run-" in message for message in caplog.messages)
