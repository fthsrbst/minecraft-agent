from pathlib import Path

import pytest

from agent_core.commands import CommandError, Vocabulary, parse_command
from agent_core.memory.places import PlaceError, PlaceStore
from agent_core.plugins import JsonObject

VOCABULARY = Vocabulary.from_handshake(
    {
        "prefix": "#",
        "commands": [
            {
                "name": "goto",
                "usage": "#goto <x> <y> <z> | #goto <place>",
                "description": "go",
                "args": [{"name": "target", "type": "position"}],
                "code": "await bot.goTo();",
            },
            {
                "name": "mine",
                "usage": "#mine <block> [count]",
                "description": "mine",
                "args": [
                    {"name": "block", "type": "word"},
                    {"name": "count", "type": "int", "default": 1, "min": 1, "max": 64},
                ],
                "code": "await bot.collect();",
            },
            {
                "name": "follow",
                "usage": "#follow [player]",
                "description": "follow",
                "args": [{"name": "player", "type": "player", "default": "$sender"}],
                "code": "x",
            },
            {
                "name": "stop",
                "usage": "#stop",
                "description": "stop",
                "args": [],
                "builtin": "stop",
            },
        ],
    }
)
PLACES: dict[str, JsonObject] = {"home": {"x": 1.0, "y": 64.0, "z": -2.0}}


def parse(text: str) -> JsonObject | None:
    invocation = parse_command(text, VOCABULARY, sender="Fatih", places=PLACES.get)
    return None if invocation is None else {"name": invocation.spec.name, **invocation.args}


def test_plain_chat_is_not_a_command() -> None:
    assert parse("hello there") is None
    assert parse("#") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#goto 10 64 -3", {"name": "goto", "target": {"x": 10.0, "y": 64.0, "z": -3.0}}),
        ("#goto home", {"name": "goto", "target": {"x": 1.0, "y": 64.0, "z": -2.0}}),
        ("#mine oak_log 5", {"name": "mine", "block": "oak_log", "count": 5}),
        ("#mine stone", {"name": "mine", "block": "stone", "count": 1}),
        ("#follow", {"name": "follow", "player": "Fatih"}),
        ("  #STOP  ", {"name": "stop"}),
    ],
)
def test_commands_parse_with_types_and_defaults(text: str, expected: JsonObject) -> None:
    assert parse(text) == expected


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("#fly", "unknown command #fly"),
        ("#goto", "missing position"),
        ("#goto nowhere", "no place called 'nowhere'"),
        ("#mine", "missing block"),
        ("#mine stone lots", "count must be a whole number"),
        ("#mine stone 500", "at most 64"),
        ("#mine stone 2 extra", "unexpected 'extra'"),
        ("#stop " + "x " * 9, "too many"),
    ],
)
def test_bad_commands_explain_themselves(text: str, message: str) -> None:
    with pytest.raises(CommandError, match=message):
        parse(text)


def test_places_survive_a_new_store_and_are_per_world(tmp_path: Path) -> None:
    store = PlaceStore(tmp_path / "places.sqlite")
    store.save("seed1", "Home", (1.5, 64.0, -3.0), dimension="overworld", saved_by="Fatih")
    store.close()
    reopened = PlaceStore(tmp_path / "places.sqlite")
    home = reopened.get("seed1", "home")
    assert home is not None and (home.x, home.z, home.saved_by) == (1.5, -3.0, "Fatih")
    assert reopened.get("seed2", "home") is None
    assert [p.name for p in reopened.all("seed1")] == ["home"]
    with pytest.raises(PlaceError):
        reopened.save("seed1", "my house!", (0, 0, 0))
