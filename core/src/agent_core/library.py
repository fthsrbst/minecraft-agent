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
# Names a skill may not have: the skill scope (`bot`, `args`, `log`) and JavaScript's reserved
# words (a skill named `for` would turn every `for (` into a call).
RESERVED_NAMES = frozenset(
    {
        "bot",
        "args",
        "log",
        "arguments",
        "eval",
        "undefined",
        "await",
        "async",
        "break",
        "case",
        "catch",
        "class",
        "const",
        "continue",
        "debugger",
        "default",
        "delete",
        "do",
        "else",
        "enum",
        "export",
        "extends",
        "false",
        "finally",
        "for",
        "function",
        "if",
        "implements",
        "import",
        "in",
        "instanceof",
        "interface",
        "let",
        "new",
        "null",
        "package",
        "private",
        "protected",
        "public",
        "return",
        "static",
        "super",
        "switch",
        "this",
        "throw",
        "true",
        "try",
        "typeof",
        "var",
        "void",
        "while",
        "with",
        "yield",
    }
)
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


_COMMENTS_AND_STRINGS = re.compile(
    r"""//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`"""
)


def code_only(code: str) -> str:
    """The code without comments and string literals: a name mentioned there is not a call."""
    return _COMMENTS_AND_STRINGS.sub(" ", code)


def _calls(code: str, names: Iterable[str]) -> set[str]:
    # A call is `name(` not preceded by `.`, a letter or `$`: `bot.craft(` is not a call of `craft`.
    plain = code_only(code)
    return {name for name in names if re.search(rf"(?<![.\w$]){re.escape(name)}\s*\(", plain)}


def calls(code: str, name: str) -> bool:
    """True when the code really calls `name(...)` (not in a comment, a string or as a method)."""
    return bool(_calls(code, [name]))


def declared_names(code: str) -> set[str]:
    """Names the code declares at any level (`const x`, `let x`, `function x`, `class x`)."""
    plain = code_only(code)
    found = re.findall(r"\b(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)", plain)
    return set(found)


class SkillLibrary:
    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self.path = path
        self.read_only = read_only
        if read_only:
            # SQLite itself refuses writes, so a frozen arm cannot change the library by accident.
            if not path.exists():
                raise LibraryError(f"no skill library at {path} to use read-only")
            self._db = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
            return
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
        """Code with the definitions of every library skill it uses in front; and their names.

        Raises LibraryError when the code declares a name a needed library skill already has:
        the two definitions would collide in one scope.
        """
        needed = self.dependencies(code)
        names = {skill.name for skill in needed}
        clashes = sorted(names & declared_names(code))
        if clashes:
            raise LibraryError(
                f"the code declares {', '.join(clashes)}, which is a library skill name; "
                "rename your helper or call the library skill instead"
            )
        needed += [skill for skill in extra if skill.name not in names]
        definitions = [
            f"// library skill: {skill.name} (v{skill.version})\n"
            f"async function {skill.name}(args = {{}}) {{\n{skill.code}\n}}"
            for skill in needed
        ]
        return "\n\n".join([*definitions, code]), [skill.name for skill in needed]
