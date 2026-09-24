"""A profile parsed from data, and the ways a shipped profile can be malformed."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from keelline.errors import Refusal
from keelline.findings import Severity
from keelline.profiles import load_profile, shipped
from keelline.profiles.model import CheckKind, ProfileError, parse

GOOD = """
detect = ["manifest.cfg", "lock-*.txt"]
scope = ["**/*.src"]

[[check]]
id = "lock-absent"
kind = "present"
level = "advice"
remedy = "commit a lock"
locators = [{at = "lock-*.txt"}]

[[check]]
id = "setting-capped"
kind = "absent"
level = "warning"
remedy = "remove the cap"
locators = [{at = "manifest.cfg", ini = ["project", "version"], match = "<"}]
"""
RULES = """# Demo

## Before the first command

- run through the tool,
  never around it
- lock after editing

## Everything else

- prose
"""


def _tree(tmp_path: Path, name: str = "demo", text: str = GOOD, rules: str | None = RULES) -> Path:
    directory = tmp_path / "profiles" / name
    directory.mkdir(parents=True)
    (directory / "profile.toml").write_text(text, encoding="utf-8")
    if rules is not None:
        (directory / "rules.md").write_text(rules, encoding="utf-8")
    return tmp_path / "profiles"


def test_a_profile_is_read_whole_from_its_directory(tmp_path: Path) -> None:
    profile = load_profile("demo", source=_tree(tmp_path))
    assert profile.name == "demo"
    assert profile.detect == ("manifest.cfg", "lock-*.txt")
    assert profile.scope == ("**/*.src",)
    assert [c.id for c in profile.checks] == ["lock-absent", "setting-capped"]
    assert profile.checks[1].kind is CheckKind.ABSENT
    assert profile.checks[1].level is Severity.WARNING
    assert profile.checks[1].locators[0].ini == ("project", "version")
    assert profile.rules == RULES


def test_the_essentials_are_the_bullets_of_the_rules_own_marked_section(tmp_path: Path) -> None:
    # One source: the region hands every harness these lines, and they are the rules' words.
    # A continuation line joins its bullet; the next heading ends the section.
    profile = load_profile("demo", source=_tree(tmp_path))
    assert profile.essentials == ("run through the tool, never around it", "lock after editing")


def test_only_a_directory_holding_a_profile_file_is_a_profile(tmp_path: Path) -> None:
    source = _tree(tmp_path)
    (source / "__pycache__").mkdir()
    (source / "notes.md").write_text("", encoding="utf-8")
    assert shipped(source=source) == ("demo",)


def test_a_name_that_is_not_shipped_is_refused_without_being_quoted(tmp_path: Path) -> None:
    with pytest.raises(ProfileError) as caught:
        load_profile("../etc", source=_tree(tmp_path))
    assert "../etc" not in str(caught.value)


def test_a_profile_without_its_rules_is_a_defect_not_an_empty_rule(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match=r"rules\.md"):
        load_profile("demo", source=_tree(tmp_path, rules=None))


def test_a_profile_error_is_a_refusal_so_it_exits_2() -> None:
    # Exit 1 means findings; a defect in Keelline's own data is exit 2 with every refusal.
    # Mutation: derive `ProfileError` from `Failure` (import `Failure as Refusal` in the model)
    # -> reddens.
    assert issubclass(ProfileError, Refusal)


@pytest.mark.parametrize(
    ("change", "fault"),
    [
        (('kind = "present"', 'kind = "matches"'), "kind"),
        (('level = "advice"', 'level = "fatal"'), "level"),
        (('match = "<"', 'match = "("'), "match"),
        ((', match = "<"', ""), "match"),
        (('ini = ["project", "version"]', 'ini = "project.version"'), "ini"),
        (('{at = "lock-*.txt"}', '{at = "../lock.txt"}'), "at"),
        (('{at = "lock-*.txt"}', '{at = "./lock.txt"}'), "at"),
        (('{at = "lock-*.txt"}', '{at = "lock.txt/"}'), "at"),
        (('id = "lock-absent"', 'id = "Lock Absent"'), "id"),
        (('scope = ["**/*.src"]', "scope = []"), "scope"),
    ],
    ids=[
        "kind",
        "level",
        "bad-regex",
        "absent-without-match",
        "ini-not-a-pair",
        "escaping-at",
        "dot-at",
        "trailing-slash-at",
        "id-grammar",
        "empty-scope",
    ],
)
def test_a_malformed_shipped_profile_is_refused_naming_what_is_wrong(
    change: tuple[str, str], fault: str
) -> None:
    # A shipped profile is Keelline's own data, so a fault here is a defect in the build, raised
    # rather than skipped: a check that silently vanished would read as a repository passing it.
    # `./lock.txt` and `lock.txt/` are the spellings `contained()` refuses at every run, so a
    # check written with one would be dead rather than wrong. Mutation: drop `_root_relative`'s
    # `checked_components` call -> `escaping-at`, `dot-at` and `trailing-slash-at` redden.
    text = GOOD.replace(*change)
    assert text != GOOD
    with pytest.raises(ProfileError, match=fault):
        parse("demo", tomllib.loads(text), RULES)


@pytest.mark.parametrize(
    "rules",
    [
        "# Demo\n",
        "# Demo\n\n## Before the first command\n\n## Next\n",
        RULES.replace("- run", "run"),
    ],
    ids=["no-section", "empty-section", "prose-in-section"],
)
def test_the_marked_section_is_required_and_holds_only_a_list(rules: str) -> None:
    with pytest.raises(ProfileError, match="Before the first command"):
        parse("demo", tomllib.loads(GOOD), rules)
