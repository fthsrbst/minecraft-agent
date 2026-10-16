from pathlib import Path

import pytest

from agent_core.library import LibraryError, SkillLibrary, tokens


@pytest.fixture
def library(tmp_path: Path) -> SkillLibrary:
    lib = SkillLibrary(tmp_path / "skills.sqlite")
    lib.add("collectLogs", "Collect logs of the nearest tree kind.", "return 1;", "t1")
    lib.add(
        "craftWoodenPickaxe", "Make a wooden pickaxe from nothing.", "await collectLogs();", "t2"
    )
    lib.add("buildShelter", "Build a small dirt shelter for the night.", "return 3;", "t3")
    return lib


def test_tokens_split_identifiers_and_drop_stop_words() -> None:
    assert tokens("craftWoodenPickaxe for the night") == ["craft", "wooden", "pickaxe", "night"]


def test_search_ranks_by_rare_shared_words(library: SkillLibrary) -> None:
    found = library.search("craft a stone pickaxe", k=2)
    assert [skill.name for skill in found] == ["craftWoodenPickaxe"]
    assert library.search("fly to the moon") == []


def test_dependencies_are_transitive_and_ordered(library: SkillLibrary) -> None:
    code = "await craftWoodenPickaxe(); return true;"
    assert [s.name for s in library.dependencies(code)] == ["collectLogs", "craftWoodenPickaxe"]


def test_assemble_defines_used_skills_before_the_code(library: SkillLibrary) -> None:
    assembled, used = library.assemble("return await craftWoodenPickaxe();")
    assert used == ["collectLogs", "craftWoodenPickaxe"]
    assert assembled.index("async function collectLogs(args = {})") < assembled.index(
        "async function craftWoodenPickaxe(args = {})"
    )
    assert assembled.endswith("return await craftWoodenPickaxe();")


def test_cycles_do_not_loop(tmp_path: Path) -> None:
    lib = SkillLibrary(tmp_path / "s.sqlite")
    lib.add("pingPong", "a", "await pongPing();", "t")
    lib.add("pongPing", "b", "await pingPong();", "t")
    assert sorted(s.name for s in lib.dependencies("await pingPong();")) == ["pingPong", "pongPing"]


def test_a_new_version_replaces_the_old_one(library: SkillLibrary) -> None:
    library.add("collectLogs", "Better.", "return 2;", "t9")
    skill = library.get("collectLogs")
    assert skill is not None
    assert (skill.version, skill.code) == (2, "return 2;")


def test_snapshot_id_changes_with_content(library: SkillLibrary, tmp_path: Path) -> None:
    before = library.snapshot_id()
    library.add("digDown", "Dig down a few blocks.", "return 4;", "t4")
    assert library.snapshot_id() != before
    assert SkillLibrary(tmp_path / "empty.sqlite").snapshot_id() == "empty"


def test_frozen_library_refuses_writes(library: SkillLibrary) -> None:
    frozen = SkillLibrary(library.path, read_only=True)
    with pytest.raises(LibraryError, match="frozen"):
        frozen.add("newSkill", "x", "return 1;", "t")
    assert len(frozen.all()) == 3


@pytest.mark.parametrize("name", ["Craft", "x", "bot", "has space", "craft-pickaxe", "a" * 60])
def test_bad_names_are_refused(library: SkillLibrary, name: str) -> None:
    with pytest.raises(LibraryError):
        library.add(name, "x", "return 1;", "t")


def test_record_use_counts(library: SkillLibrary) -> None:
    library.record_use(["collectLogs", "collectLogs"])
    skill = library.get("collectLogs")
    assert skill is not None and skill.uses == 2
