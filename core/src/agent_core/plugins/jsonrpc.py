"""JSON-RPC 2.0 message shapes for the Game Plugin Protocol (one JSON message per line)."""

import json
from typing import cast

# The protocol version the core speaks; a plugin must declare the same one in its manifest.
PROTOCOL_VERSION = "gpp/1"

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]


def encode_request(request_id: int, method: str, params: JsonObject) -> bytes:
    message: JsonObject = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    # One message per line: json.dumps never emits raw newlines, so the line framing is safe.
    return json.dumps(message, separators=(",", ":")).encode() + b"\n"


def decode_message(line: bytes) -> JsonObject | None:
    """Decodes one line; returns None if it is not a JSON object (the caller logs and skips it)."""
    try:
        message: object = json.loads(line)
    except (ValueError, RecursionError):
        # ValueError covers invalid JSON and non-UTF-8 bytes; RecursionError very deep nesting.
        return None
    if not isinstance(message, dict):
        return None
    return cast(JsonObject, message)
