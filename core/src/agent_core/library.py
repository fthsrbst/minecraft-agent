"""The skill library: verified skills, found again by keywords and reused by later skills.

A skill is stored only after its task's predicate verified it (AGENTS.md decision 6). Later code
calls a stored skill by name; `assemble` puts the definitions it needs (and theirs, recursively)
in front of the new code, so skill code stays a plain function body for the plugin's executor.
The library knows nothing about any game: names, descriptions and code are opaque text.
"""

import hashlib
import math
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# camelCase identifiers: valid JavaScript names that cannot shadow the skill API (`bot`, `args`,
# `log`) or a language keyword in practice.
NAME_PATTERN = re.compile(r"^[a-z][a-zA-Z0-9]{2,47}$")
RESERVED_NAMES = frozenset({"bot", "args", "log", "await", "async", "function", "return"})
MAX_DESCRIPTION = 500
_STOP_WORDS = frozenset(
    {"a", "an", "and", "the", "of", "to", "in", "on", "for", "with", "from", "at", "by", "it", "is"}
)


class LibraryError(ValueError):
    """A skill cannot be stored (bad name, empty code, read-only library)."""


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    code: str
    source_task: str
    version: int = 1
    uses: int = 0
    created_at: str = ""


def tokens(text: str) -> list[str]:
    """Words of a text or identifier: `craftWoodenPickaxe` → craft, wooden, pickaxe."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    words = re.findall(r"[a-z0-9]+", spaced.lower())
    return [word for word in words if word not in _STOP_WORDS and len(word) > 1]


def _calls(code: str, names: Iterable[str]) -> set[str]:
    return {name for name in names if re.search(rf"\b{re.escape(name)}\s*\(", code)}


class SkillLibrary:
    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self.path = path
        self.read_only = read_only
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS skills (
                name TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                code TEXT NOT NULL,
                source_task TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                uses INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def add(self, name: str, description: str, code: str, source_task: str) -> Skill:
        """Stores a verified skill; a new version replaces an older skill of the same name."""
        if self.read_only:
            raise LibraryError("the library is frozen (read-only) for this run")
        if not NAME_PATTERN.fullmatch(name) or name in RESERVED_NAMES:
            raise LibraryError(f"skill name {name!r} must be camelCase, 3 to 48 characters")
        if not code.strip():
            raise LibraryError("skill code is empty")
        existing = self.get(name)
        version = 1 if existing is None else existing.version + 1
        created = datetime.now(UTC).isoformat()
        self._db.execute(
            "INSERT OR REPLACE INTO skills VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, description[:MAX_DESCRIPTION], code, source_task, version, 0, created),
        )
        self._db.commit()
        return Skill(name, description[:MAX_DESCRIPTION], code, source_task, version, 0, created)

    def get(self, name: str) -> Skill | None:
        row = self._db.execute("SELECT * FROM skills WHERE name = ?", (name,)).fetchone()
        return None if row is None else Skill(*row)

    def all(self) -> list[Skill]:
        return [Skill(*row) for row in self._db.execute("SELECT * FROM skills ORDER BY name")]

    def record_use(self, names: Iterable[str]) -> None:
        if self.read_only:
            return
        self._db.executemany(
            "UPDATE skills SET uses = uses + 1 WHERE name = ?", [(name,) for name in names]
        )
        self._db.commit()

    def snapshot_id(self) -> str:
        """Identifies this exact library content; written into every run record (decision 14)."""
        skills = self.all()
        if not skills:
            return "empty"
        digest = hashlib.sha256()
        for skill in skills:
            digest.update(f"{skill.name}\0{skill.code}\0".encode())
        return f"{len(skills)}-{digest.hexdigest()[:12]}"

    def search(self, query: str, k: int = 3) -> list[Skill]:
        """Best keyword matches: word overlap weighted by how rare a word is in the library."""
        skills = self.all()
        wanted = Counter(tokens(query))
        if not skills or not wanted:
            return []
        documents = [set(tokens(f"{s.name} {s.description}")) for s in skills]
        frequency = Counter(word for words in documents for word in words)
        scored: list[tuple[float, Skill]] = []
        for skill, words in zip(skills, documents, strict=True):
            score = sum(
                math.log(1 + len(skills) / frequency[word]) for word in wanted if word in words
            )
            if score > 0:
                scored.append((score, skill))
        scored.sort(key=lambda pair: (-pair[0], pair[1].name))
        return [skill for _, skill in scored[:k]]

    def dependencies(self, code: str) -> list[Skill]:
        """Library skills the code calls, directly or through each other, dependencies first."""
        by_name = {skill.name: skill for skill in self.all()}
        ordered: list[Skill] = []
        seen: set[str] = set()

        def visit(source: str, path: tuple[str, ...]) -> None:
            for name in sorted(_calls(source, by_name)):
                if name in seen or name in path:
                    continue  # already included, or a cycle: each definition appears once
                visit(by_name[name].code, (*path, name))
                seen.add(name)
                ordered.append(by_name[name])

        visit(code, ())
        return ordered

    def assemble(self, code: str, extra: Sequence[Skill] = ()) -> tuple[str, list[str]]:
        """Code with the definitions of every library skill it uses in front; and their names."""
        needed = self.dependencies(code)
        names = {skill.name for skill in needed}
        needed += [skill for skill in extra if skill.name not in names]
        definitions = [
            f"// library skill: {skill.name} (v{skill.version})\n"
            f"async function {skill.name}(args = {{}}) {{\n{skill.code}\n}}"
            for skill in needed
        ]
        return "\n\n".join([*definitions, code]), [skill.name for skill in needed]
