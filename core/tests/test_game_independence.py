"""Guards the rule that the core never knows a specific game.

Game names and game library names in `src/` mean game code leaked into the core;
the fix is a generic plugin-contract extension, not an exception in this list.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

FORBIDDEN = re.compile(r"minecraft|mineflayer|prismarine|vizdoom|doom", re.IGNORECASE)


def find_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if FORBIDDEN.search(line):
                violations.append(f"{path.relative_to(root)}:{number}: {line.strip()}")
    return violations


def test_core_source_has_no_game_specific_names() -> None:
    assert find_violations(SRC) == []


def test_detector_catches_a_leak(tmp_path: Path) -> None:
    (tmp_path / "leak.py").write_text('BLOCK = "minecraft:stone"\n', encoding="utf-8")
    assert find_violations(tmp_path) == ['leak.py:1: BLOCK = "minecraft:stone"']
