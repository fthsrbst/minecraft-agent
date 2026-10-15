"""Game plugins: loading manifests and talking to plugin processes over JSON-RPC."""

from agent_core.plugins.client import (
    PluginClient,
    PluginError,
    PluginExitedError,
    PluginRpcError,
)
from agent_core.plugins.jsonrpc import PROTOCOL_VERSION, JsonObject, JsonValue
from agent_core.plugins.manifest import ManifestError, PluginManifest, load_manifest

__all__ = [
    "PROTOCOL_VERSION",
    "JsonObject",
    "JsonValue",
    "ManifestError",
    "PluginClient",
    "PluginError",
    "PluginExitedError",
    "PluginManifest",
    "PluginRpcError",
    "load_manifest",
]
