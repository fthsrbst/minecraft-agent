"""Named places per world (plan P3.3).

"Where is home?" is a lookup, not a search: places are rows in SQLite keyed by world and name,
so they survive restarts and never drift (no RAG for coordinates).
"""

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PLACE_NAME = re.compile(r"^[a-z0-9_-]{1,32}$")


class PlaceError(ValueError):
    """A place name is invalid; the message is meant for the player."""


@dataclass(frozen=True, slots=True)
class Place:
    world: str
    name: str
    x: float
    y: float
    z: float
    dimension: str | None
    saved_by: str | None
    saved_at: str


class PlaceStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS places (
                world TEXT NOT NULL, name TEXT NOT NULL,
                x REAL NOT NULL, y REAL NOT NULL, z REAL NOT NULL,
                dimension TEXT, saved_by TEXT, saved_at TEXT NOT NULL,
                PRIMARY KEY (world, name)
            )
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def save(
        self,
        world: str,
        name: str,
        position: tuple[float, float, float],
        *,
        dimension: str | None = None,
        saved_by: str | None = None,
    ) -> Place:
        key = name.lower()
        if not PLACE_NAME.fullmatch(key):
            raise PlaceError("place names are 1-32 letters, digits, - or _")
        place = Place(world, key, *position, dimension, saved_by, datetime.now(UTC).isoformat())
        self._db.execute(
            "INSERT OR REPLACE INTO places VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                place.world,
                place.name,
                place.x,
                place.y,
                place.z,
                dimension,
                saved_by,
                place.saved_at,
            ),
        )
        self._db.commit()
        return place

    def get(self, world: str, name: str) -> Place | None:
        row = self._db.execute(
            "SELECT * FROM places WHERE world = ? AND name = ?", (world, name.lower())
        ).fetchone()
        return None if row is None else Place(*row)

    def all(self, world: str) -> list[Place]:
        rows = self._db.execute("SELECT * FROM places WHERE world = ? ORDER BY name", (world,))
        return [Place(*row) for row in rows]
