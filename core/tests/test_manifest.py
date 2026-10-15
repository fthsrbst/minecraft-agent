import json
import sys
from pathlib import Path

import pytest

from agent_core.plugins import PROTOCOL_VERSION, ManifestError, load_manifest
from agent_core.plugins.jsonrpc import JsonObject


def write_manifest(directory: Path, **overrides: object) -> Path:
    manifest: dict[str, object] = {
        "id": "fake",
        "version": "1.2.3",
        "protocolVersion": PROTOCOL_VERSION,
        "game": {"name": "Fake Game"},
        "command": [sys.executable, "main.py"],
        "capabilities": ["scenario"],
    }
    manifest.update(overrides)
    (directory / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory


def test_loads_a_valid_manifest(tmp_path: Path) -> None:
    manifest = load_manifest(write_manifest(tmp_path))
    assert manifest.id == "fake"
    assert manifest.version == "1.2.3"
    assert manifest.game == {"name": "Fake Game"}
    assert manifest.command == (sys.executable, "main.py")
    assert manifest.capabilities == ("scenario",)
    assert manifest.directory == tmp_path.resolve()


def test_the_repository_plugin_manifest_is_valid() -> None:
    # Every plugin shipped in the repository must load; this test names no game.
    plugins_root = Path(__file__).resolve().parents[2] / "plugins"
    manifests = sorted(plugins_root.glob("*/plugin.json"))
    assert manifests, "expected at least one plugin in plugins/"
    for path in manifests:
        data: JsonObject = json.loads(path.read_text(encoding="utf-8"))
        assert data["protocolVersion"] == PROTOCOL_VERSION
        load_manifest(path.parent)


def test_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match=r"No plugin\.json"):
        load_manifest(tmp_path)


def test_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "plugin.json").write_text("{", encoding="utf-8")
    with pytest.raises(ManifestError, match="invalid JSON"):
        load_manifest(tmp_path)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"protocolVersion": "gpp/0"}, "this core speaks gpp/1"),
        ({"id": ""}, "`id` must be a non-empty string"),
        ({"command": []}, "`command` must not be empty"),
        ({"command": "node main.js"}, "`command` must be a list of strings"),
        ({"command": ["no-such-executable-xyz"]}, "was not found on PATH"),
        ({"capabilities": [1]}, "`capabilities` must be a list of strings"),
        ({"game": []}, "`game` must be an object"),
    ],
)
def test_rejects_bad_fields(tmp_path: Path, overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ManifestError, match=message):
        load_manifest(write_manifest(tmp_path, **overrides))
