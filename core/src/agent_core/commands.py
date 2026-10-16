"""`#command` parsing (plan P3.2): generic syntax, vocabulary from the plugin's handshake.

The core knows the grammar (`#name arg arg …`) and the argument types; the plugin decides which
commands exist and what they do. A position argument may be a remembered place name, resolved
by the caller (places are core memory, P3.3).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from agent_core.plugins import JsonObject, JsonValue

MAX_ARGS = 8
MAX_ARG_LENGTH = 64


class CommandError(ValueError):
    """The text is a command but cannot be used; the message is meant for the player."""


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    usage: str
    description: str
    args: tuple[JsonObject, ...]
    code: str | None = None
    builtin: str | None = None


@dataclass(frozen=True, slots=True)
class Invocation:
    spec: CommandSpec
    args: JsonObject = field(default_factory=dict[str, JsonValue])


@dataclass(frozen=True, slots=True)
class Vocabulary:
    prefix: str
    commands: Mapping[str, CommandSpec]

    @staticmethod
    def from_handshake(value: JsonValue) -> "Vocabulary":
        if not isinstance(value, dict):
            return Vocabulary("#", {})
        prefix = value.get("prefix")
        specs: dict[str, CommandSpec] = {}
        commands = value.get("commands")
        for entry in commands if isinstance(commands, list) else []:
            if not isinstance(entry, dict):
                continue
            name, args = entry.get("name"), entry.get("args")
            code, builtin = entry.get("code"), entry.get("builtin")
            if not isinstance(name, str) or not isinstance(args, list):
                continue
            specs[name] = CommandSpec(
                name,
                str(entry.get("usage", f"#{name}")),
                str(entry.get("description", "")),
                tuple(arg for arg in args if isinstance(arg, dict)),
                code if isinstance(code, str) else None,
                builtin if isinstance(builtin, str) else None,
            )
        return Vocabulary(prefix if isinstance(prefix, str) and prefix else "#", specs)

    def help_lines(self) -> list[str]:
        return [f"{spec.usage}: {spec.description}" for spec in self.commands.values()]


PlaceLookup = Callable[[str], JsonObject | None]


def _number(text: str, name: str, *, integer: bool) -> float | int:
    try:
        value = int(text) if integer else float(text)
    except ValueError:
        kind = "a whole number" if integer else "a number"
        raise CommandError(f"{name} must be {kind}, not {text!r}") from None
    if not integer and value != value:  # NaN
        raise CommandError(f"{name} must be a number")
    return value


def _bounded(value: float | int, arg: JsonObject, name: str) -> float | int:
    low, high = arg.get("min"), arg.get("max")
    if isinstance(low, int | float) and value < low:
        raise CommandError(f"{name} must be at least {low}")
    if isinstance(high, int | float) and value > high:
        raise CommandError(f"{name} must be at most {high}")
    return value


def parse_command(
    text: str, vocabulary: Vocabulary, *, sender: str, places: PlaceLookup
) -> Invocation | None:
    """None if the text is not a command; CommandError if it is one but cannot be used."""
    stripped = text.strip()
    if not stripped.startswith(vocabulary.prefix):
        return None
    words = stripped[len(vocabulary.prefix) :].split()
    if not words:
        return None
    name, values = words[0].lower(), words[1:]
    spec = vocabulary.commands.get(name)
    if spec is None:
        raise CommandError(
            f"unknown command {vocabulary.prefix}{name}; try {vocabulary.prefix}help"
        )
    if len(values) > MAX_ARGS or any(len(value) > MAX_ARG_LENGTH for value in values):
        raise CommandError(f"too many or too long arguments; usage: {spec.usage}")

    parsed: JsonObject = {}
    queue: list[str] = list(values)
    for arg in spec.args:
        name_value = arg.get("name")
        arg_name = name_value if isinstance(name_value, str) else "argument"
        kind = arg.get("type")
        if kind == "position":
            parsed[arg_name] = _position(queue, places, spec)
            continue
        if not queue:
            default = arg.get("default")
            if default is None:
                raise CommandError(f"missing {arg_name}; usage: {spec.usage}")
            parsed[arg_name] = sender if default == "$sender" else default
            continue
        raw = queue.pop(0)
        if kind == "int":
            parsed[arg_name] = _bounded(_number(raw, arg_name, integer=True), arg, arg_name)
        elif kind == "number":
            parsed[arg_name] = _bounded(_number(raw, arg_name, integer=False), arg, arg_name)
        else:  # word, player
            parsed[arg_name] = raw
    if queue:
        raise CommandError(f"unexpected {' '.join(queue)!r}; usage: {spec.usage}")
    return Invocation(spec, parsed)


def _position(queue: list[str], places: PlaceLookup, spec: CommandSpec) -> JsonObject:
    if not queue:
        raise CommandError(f"missing position; usage: {spec.usage}")
    if len(queue) >= 3:
        try:
            x, y, z = (float(queue[i]) for i in range(3))
        except ValueError:
            pass
        else:
            del queue[:3]
            return {"x": x, "y": y, "z": z}
    place = queue.pop(0)
    found = places(place)
    if found is None:
        raise CommandError(f"no place called {place!r}; save one with #sethome {place}")
    return found


def describe(commands: Sequence[CommandSpec]) -> str:
    return "\n".join(f"- {spec.usage}: {spec.description}" for spec in commands)
