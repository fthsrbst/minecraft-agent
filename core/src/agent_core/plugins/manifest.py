"""The plugin manifest (`plugin.json`): what a plugin is and how to start it."""

import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from agent_core.plugins.jsonrpc import PROTOCOL_VERSION, JsonObject, JsonValue

MANIFEST_FILE = "plugin.json"


class ManifestError(Exception):
    """The plugin manifest is missing, malformed, or incompatible with this core."""


@dataclass(frozen=True, slots=True)
class PluginManifest:
    id: str
    version: str
    protocol_version: str
    game: JsonObject
    command: tuple[str, ...]
    capabilities: tuple[str, ...]
    directory: Path
    # Optional extra processes, e.g. "scenario" for the evaluator; started on request only.
    components: Mapping[str, tuple[str, ...]] = field(default_factory=dict[str, tuple[str, ...]])
    # Environment variables each process may receive (key None = the main process).
    env: Mapping[str | None, tuple[str, ...]] = field(
        default_factory=dict[str | None, tuple[str, ...]]
    )

    def env_for(self, component: str | None) -> tuple[str, ...]:
        self.command_for(component)  # raises for an unknown component
        return self.env.get(component, ())

    def command_for(self, component: str | None) -> tuple[str, ...]:
        if component is None:
            return self.command
        try:
            return self.components[component]
        except KeyError:
            known = ", ".join(sorted(self.components)) or "none"
            raise ManifestError(
                f"Plugin {self.id} has no component {component!r} (known: {known})."
            ) from None


def _require_str(data: JsonObject, key: str, source: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ManifestError(f"{source}: `{key}` must be a non-empty string.")
    return value


def _require_str_list(data: JsonObject, key: str, source: Path) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ManifestError(f"{source}: `{key}` must be a list of strings.")
    return tuple(cast(list[str], value))


def _require_command(data: JsonObject, key: str, source: Path) -> tuple[str, ...]:
    command = _require_str_list(data, key, source)
    if not command:
        raise ManifestError(f"{source}: `{key}` must not be empty.")
    if shutil.which(command[0]) is None:
        raise ManifestError(f"{source}: executable `{command[0]}` was not found on PATH.")
    return command


def _optional_env(data: JsonObject, source: Path) -> tuple[str, ...]:
    return _require_str_list(data, "env", source) if "env" in data else ()


def _parse_components(
    value: JsonValue, source: Path
) -> tuple[dict[str, tuple[str, ...]], dict[str | None, tuple[str, ...]]]:
    if not isinstance(value, dict):
        raise ManifestError(f"{source}: `components` must be an object.")
    commands: dict[str, tuple[str, ...]] = {}
    env: dict[str | None, tuple[str, ...]] = {}
    for name, spec in value.items():
        if not isinstance(spec, dict):
            raise ManifestError(f"{source}: component `{name}` must be an object.")
        commands[name] = _require_command(spec, "command", source)
        env[name] = _optional_env(spec, source)
    return commands, env


def load_manifest(plugin_dir: Path) -> PluginManifest:
    source = plugin_dir / MANIFEST_FILE
    try:
        raw: JsonValue = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ManifestError(f"No {MANIFEST_FILE} in {plugin_dir}.") from None
    except json.JSONDecodeError as error:
        raise ManifestError(f"{source}: invalid JSON ({error}).") from error
    if not isinstance(raw, dict):
        raise ManifestError(f"{source}: the manifest must be a JSON object.")

    protocol_version = _require_str(raw, "protocolVersion", source)
    if protocol_version != PROTOCOL_VERSION:
        raise ManifestError(
            f"{source}: plugin speaks {protocol_version}, this core speaks {PROTOCOL_VERSION}."
        )

    command = _require_command(raw, "command", source)
    components, env = _parse_components(raw.get("components", {}), source)
    env[None] = _optional_env(raw, source)

    game = raw.get("game", {})
    if not isinstance(game, dict):
        raise ManifestError(f"{source}: `game` must be an object.")

    return PluginManifest(
        id=_require_str(raw, "id", source),
        version=_require_str(raw, "version", source),
        protocol_version=protocol_version,
        game=game,
        command=command,
        capabilities=_require_str_list(raw, "capabilities", source),
        directory=plugin_dir.resolve(),
        components=components,
        env=env,
    )
