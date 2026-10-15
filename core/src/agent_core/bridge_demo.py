"""P1.3 demo: start a plugin, handshake, print an observation, chat, move, and observe again.

    uv run python -m agent_core.bridge_demo ../plugins/<game>

The plugin must be built first, and its game server must be running.
"""

import argparse
import asyncio
import json
import logging
import math
import sys
from pathlib import Path

from agent_core.plugins import JsonObject, JsonValue, ManifestError, PluginClient, PluginError


def _horizontal_position(observation: JsonObject) -> tuple[float, float] | None:
    # Observations are opaque to the core; this demo only assumes a numeric position.x / position.z.
    position = observation.get("position")
    if not isinstance(position, dict):
        return None
    x, z = position.get("x"), position.get("z")
    if isinstance(x, int | float) and isinstance(z, int | float):
        return float(x), float(z)
    return None


def _show(title: str, value: JsonValue) -> None:
    print(f"\n== {title} ==\n{json.dumps(value, indent=2)}")


async def run(plugin_dir: Path) -> None:
    async with await PluginClient.start(plugin_dir) as plugin:
        _show("handshake", await plugin.handshake())

        before = await plugin.observe()
        _show("observation", before)

        await plugin.act("chat", {"text": "Hello from the core!"})
        moved = await plugin.act("move", {"direction": "forward", "durationMs": 1500, "jump": True})
        _show("act move", moved)

        after = await plugin.observe()
        start, end = _horizontal_position(before), _horizontal_position(after)
        if start is not None and end is not None:
            print(f"\nMoved {math.dist(start, end):.2f} blocks horizontally.")

        await asyncio.sleep(1)
        _show("events", list(plugin.drain_events()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the plugin bridge demo.")
    parser.add_argument("plugin_dir", type=Path, help="directory that contains plugin.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s", stream=sys.stderr)
    try:
        asyncio.run(run(args.plugin_dir))
    except (ManifestError, PluginError, TimeoutError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
