"""§5.8: no project-identifying string in the public repository, held over this plan's files.

The design's whole-tree gate belongs to the `workflows` lane; this is the same rule scoped to
what the three wave-2 closure ports can carry in, checked from the first task so a ported
docstring, a ported skill or a ported theme list cannot land the state §11 requires it to
shed. It walks three areas, two document trees and four shared leaf modules because one plan
delivers them, and it lives at the top level of `tests/` for that reason. It now holds two
tables: `FORBIDDEN` over the lane's source, tests and skills, and `PUBLIC_FORBIDDEN` over the
public documents the second closure plan writes. The public table is the full one minus the
digests of the default `[paths]` values the preset itself ships, read off the preset at import
time, because a README that could not say where the note store lives by default would be
useless. The lane walk is unchanged and still refuses those three: a module has no reason to
spell a default path.

**A deliberate second copy.** `tests/guards/test_neutral.py` carries the same denylist and
the same `offending()`; a twenty-first token has to be added to both tables by hand. Both
gates are deleted the day the `workflows` lane ships the whole-tree gate — do not extend
either into a third.

The denylist is stored as digests, not tokens — see tests/guards/test_neutral.py for why, and
do not "simplify" them back into literals.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LANE = (
    ROOT / "src" / "keelline" / "ledger",
    ROOT / "src" / "keelline" / "docs",
    ROOT / "tests" / "ledger",
    ROOT / "tests" / "docs",
    ROOT / "tests" / "skills",
    ROOT / "skills",
    ROOT / "agents",
)
PLANS = (
    "docs/plans/2026-09-16-wave-2-closure-ledger-docs-skills.md",
    "docs/plans/2026-09-16-wave-2-closure-readme-notes.md",
)
FRAGMENTS = ("ledger", "docs-tooling", "skills-port", "memory-refs", "readme-methodology", "notes")
# The public documents the second closure plan writes or rewrites, walked with
# `PUBLIC_FORBIDDEN` rather than the full table (see it). `docs/methodology/` is a glob so a
# fourth file there is gated the day it is added; the preset is here because that plan
# writes its `[rules]` table and a rule body is prose.
DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "src" / "keelline" / "presets" / "recommended.toml",
    ROOT / "docs" / "plans" / "README.md",
)
METHODOLOGY = ROOT / "docs" / "methodology"
# The leaf modules this plan adds beside the areas (Task 2), the one memory module it adds
# to a merged lane (Premise 8), and their tests.
EXTRA_FILES = (
    ROOT / "src" / "keelline" / "identifiers.py",
    ROOT / "src" / "keelline" / "findings.py",
    ROOT / "src" / "keelline" / "command.py",
    ROOT / "src" / "keelline" / "prose.py",
    ROOT / "src" / "keelline" / "memory" / "refs.py",
    ROOT / "tests" / "test_identifiers.py",
    ROOT / "tests" / "test_findings.py",
    ROOT / "tests" / "test_command.py",
    ROOT / "tests" / "test_git_run.py",
    ROOT / "tests" / "memory" / "test_refs.py",
)


def _digest(window: bytes) -> str:
    return hashlib.blake2s(window, digest_size=6).hexdigest()


def digest_of(token: str) -> str:
    """The stored form of one denylist token: twelve hex characters, not eight.

    Eight would be a lower-case hex run of exactly the length the `bare commit id` arm below
    matches, and these digests are quoted in the plan, which this gate walks.
    """
    return _digest(token.lower().encode("utf-8"))


# `(length, digest)` per lower-cased substring. Each stands for a path, identifier or name that
# belongs to the repository the guards were extracted from and to no other; none is a word a
# neutral guard needs. The module docstring says why they are digests rather than the strings.
FORBIDDEN = (
    (7, "41d4469bc846"),
    (6, "7f5fd64931a1"),
    (16, "5b958322253b"),
    (10, "3b2506f40a57"),
    (15, "d67aef39d5ec"),
    (22, "084d395e2884"),
    (17, "f88e4d57bd04"),
    (13, "19a6183f34da"),
    (8, "5a6645d31f46"),
    (16, "96f4afbf58ea"),
    (11, "cbab126d3cca"),
    (13, "4ed3b2917da0"),
    (17, "804de1d3098a"),
    (9, "5f65f06d6470"),
    (9, "453c2632b940"),
    (8, "6144c481add3"),
    (8, "54b030106757"),
    (4, "dea22fd6c241"),
    (4, "188937a5982a"),
    (8, "4d1fd41cacbb"),
)
# Shapes a substring list cannot express: a personal address, a bare commit id, a
# vendor-prefixed branch name. Each arm is named so a hit says what it is.
SHAPES = (
    # Not `@users.noreply.github.com`: that is GitHub's generic form and a Task 5 negative.
    ("personal email", re.compile(r"@(?:gmail|yandex|mail|icloud|proton)\.\w+")),
    # At least one digit, so an eight-letter hex word (`deadbeef`) is not an id.
    ("bare commit id", re.compile(r"(?<![\w/])(?=[0-9a-f]*\d)[0-9a-f]{8,10}(?![\w/])")),
    # `(?<![.\w/])`: `.claude/settings.json` and `.codex/hooks.json` are harness directories a
    # public document has to be able to name, and a documentation URL can carry `/codex/` as a
    # path segment; a branch name is never preceded by a dot or a slash.
    ("vendor branch", re.compile(r"(?<![.\w/])(?:codex|claude|cursor)/[a-z0-9][\w-]*")),
)


def offending(text: str, forbidden: tuple[tuple[int, str], ...] = FORBIDDEN) -> list[str]:
    """Every denylist digest and every shape name the text hits.

    A hashed denylist cannot be substring-matched, so the text is scanned by window: for each
    stored length, every window of that length in the lower-cased bytes is hashed and the
    digests are intersected with the entries of that length. Every token is ASCII, so a window
    over bytes and a substring of the string agree, and this is exactly the `token in lowered`
    it replaces.
    """
    raw = text.lower().encode("utf-8")
    found: list[str] = []
    for width in sorted({width for width, _ in forbidden}):
        wanted = {digest for length, digest in forbidden if length == width}
        seen = {_digest(raw[start : start + width]) for start in range(len(raw) - width + 1)}
        found.extend(f"token {digest}" for digest in sorted(wanted & seen))
    lowered = text.lower()
    found.extend(name for name, shape in SHAPES if shape.search(lowered))
    return found


def _preset_paths() -> tuple[tuple[int, str], ...]:
    """The digests of the default `[paths]` values the preset ships.

    Three of them are in `FORBIDDEN`, because they were the source repository's paths before
    they were Keelline's defaults. A public document that could not say where the note store
    lives by default would be useless, so the public-document walk exempts exactly the values
    the plugin itself ships — read off the preset at import time, never written here. Source
    code keeps the full table: a module has no reason to spell a default path.
    """
    from keelline.presets import load_preset

    values = load_preset("recommended")["defaults"]["paths"].values()
    return tuple((len(value), digest_of(value)) for value in values)


PUBLIC_FORBIDDEN = tuple(entry for entry in FORBIDDEN if entry not in _preset_paths())


def document_files() -> list[Path]:
    found = [*DOCUMENTS, *sorted(METHODOLOGY.glob("*.md"))]
    # Both plans, without an existence guard, for the reason `lane_files` gives.
    found.extend(ROOT / plan for plan in PLANS)
    for slug in ("readme-methodology", "notes"):
        fragment = ROOT / "changelog.d" / f"{slug}.feature.md"
        if fragment.is_file():
            found.append(fragment)
    return sorted(found)


def lane_files() -> list[Path]:
    found: list[Path] = []
    for directory in LANE:
        found.extend(directory.rglob("*.py"))
        found.extend(directory.rglob("*.md"))
    found.extend(path for path in EXTRA_FILES if path.is_file())
    # The plan is named without an existence guard on purpose — a skipped file would hide
    # exactly the drift this walk exists to catch.
    found.append(ROOT / PLANS[0])
    for slug in FRAGMENTS:
        fragment = ROOT / "changelog.d" / f"{slug}.feature.md"
        if fragment.is_file():
            found.append(fragment)
    # `docs/cli.md` and `gitenv.py` are shared, pre-existing files with Keelline's own strings
    # that hit the gate; the sections and the function this plan adds to them are checked by
    # hand at the tasks that write them.
    return sorted(path for path in found if path.name != "test_neutral_wave2.py")


def test_the_gate_reads_something() -> None:
    # No mutation of its own: this is the mutation guard for the parametrised test below,
    # which passes vacuously if the walk ever finds no files. `rglob` over a directory that
    # does not exist yet yields nothing and raises nothing, so each wave that creates a gated
    # tree extends this guard with one file from it (Tasks 2, 13 and 14) — the wave that
    # creates a tree is the wave that proves the gate reads it.
    files = lane_files()
    assert ROOT / "src" / "keelline" / "ledger" / "__init__.py" in files
    assert ROOT / "src" / "keelline" / "docs" / "__init__.py" in files
    assert ROOT / PLANS[0] in files
    assert ROOT / "src" / "keelline" / "identifiers.py" in files
    assert ROOT / "src" / "keelline" / "findings.py" in files
    assert ROOT / "skills" / "close-bug" / "SKILL.md" in files
    assert ROOT / "agents" / "code-navigator.md" in files


def test_the_denylist_is_stored_as_digests() -> None:
    # The gate that hides a name must not publish it. This reddens if anyone replaces the
    # digests with the tokens, or empties the list on the way past.
    assert len(FORBIDDEN) == 20
    assert all(length >= 4 for length, _ in FORBIDDEN)
    assert all(re.fullmatch(r"[0-9a-f]{12}", digest) for _, digest in FORBIDDEN)


def test_the_digest_function_is_pinned() -> None:
    # `test_the_gate_discriminates` builds its expected value with `digest_of`, so both sides
    # move together and it cannot pin the hash. This does: change the algorithm or the digest
    # size and every stored digest stops matching, which would leave the tree gate green while
    # checking nothing at all. Second line: the scan lower-cases, so the stored form must too.
    assert digest_of("quernstone") == "be440e8c9338"
    assert digest_of("QuernStone") == digest_of("quernstone")


def test_the_gate_discriminates() -> None:
    # The oracle for the gate itself: a token planted in a synthetic string is found, and so
    # is each regex arm; a neutral fixture is not. The planted token is a made-up word passed
    # in as a one-entry denylist, not a real `FORBIDDEN` entry — writing a real one here would
    # undo the hashing this file exists to keep.
    probe = "quernstone"
    planted = ((len(probe), digest_of(probe)),)
    assert offending("see Quernstone/plans", planted) == [f"token {digest_of(probe)}"]
    assert offending("see quernston/plans", planted) == []
    assert offending("Co-authored-by: Someone <someone@gmail.com>") == ["personal email"]
    assert offending("fixed in 1b279648") == ["bare commit id"]
    assert offending("cut from codex/inbound-remediation") == ["vendor branch"]
    assert offending("cat secrets/.env; person@example.com; 0x1234; deadbeef") == []
    assert offending("Co-authored-by: Someone <someone@users.noreply.github.com>") == []


def test_mutations_toml_carries_no_source_repository_string() -> None:
    text = (ROOT / "mutations.toml").read_text(encoding="utf-8")
    mine = (
        "keelline/ledger/",
        "keelline/docs/",
        "keelline/memory/refs.py",
        "keelline/identifiers.py",
        "keelline/findings.py",
        "keelline/command.py",
        "keelline/prose.py",
    )
    entries = [b for b in text.split("[[mutation]]") if any(name in b for name in mine)]
    for block in entries:
        assert offending(block) == [], block[:120]


@pytest.mark.parametrize("path", lane_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_lane_file_carries_a_source_repository_string(path: Path) -> None:
    assert offending(path.read_text(encoding="utf-8")) == [], path


# Three of the preset's eleven default `[paths]` values are also digest-table entries — the
# ones that were the source repository's paths before they were Keelline's defaults. Pinned so
# the exemption cannot quietly grow: a fourth would mean a token was added to the table for a
# path the plugin itself ships, which is a contradiction to resolve, not to exempt.
PRESET_PATHS_IN_TABLE = 3


def test_the_public_document_walk_is_not_empty() -> None:
    # The vacuity guard for the parametrised public walk below, the same shape as
    # `test_the_gate_reads_something` for the lane walk; named apart from it so `-k` can pick
    # one. `docs/methodology/README.md` is named because the wave that created that tree is
    # the wave that proves the gate reads it.
    files = document_files()
    assert ROOT / "README.md" in files
    assert ROOT / PLANS[1] in files
    assert ROOT / "src" / "keelline" / "presets" / "recommended.toml" in files
    assert METHODOLOGY / "README.md" in files


def test_the_exemption_is_exactly_the_presets_default_paths() -> None:
    # Reddens if the preset stops shipping a default path (the exemption shrinks and a public
    # document that names it reddens too), or if someone widens `PUBLIC_FORBIDDEN` by hand:
    # the difference between the two tables must be preset values and nothing else.
    exempt = set(FORBIDDEN) - set(PUBLIC_FORBIDDEN)
    assert exempt <= set(_preset_paths())
    assert len(exempt) == PRESET_PATHS_IN_TABLE
    # The full table's size is pinned by `test_the_denylist_is_stored_as_digests`; the lane
    # walk still refuses those three, which `test_the_public_table_still_discriminates` shows.


def test_the_public_table_still_discriminates() -> None:
    # A preset path is allowed by the public table and refused by the full one; a planted
    # token is refused by both; the dotted harness directory is not a vendor branch.
    from keelline.presets import load_preset

    a_default = next(iter(load_preset("recommended")["defaults"]["paths"].values()))
    exempt_value = next(
        value
        for value in load_preset("recommended")["defaults"]["paths"].values()
        if (len(value), digest_of(value)) in set(FORBIDDEN)
    )
    assert offending(exempt_value, PUBLIC_FORBIDDEN) == []
    assert offending(exempt_value) != []
    assert offending(a_default, PUBLIC_FORBIDDEN) == []
    probe = "quernstone"
    planted = ((len(probe), digest_of(probe)),)
    assert offending("see quernstone", planted) == [f"token {digest_of(probe)}"]
    assert offending("edit .claude/settings.json and .codex/hooks.json") == []
    assert offending("see https://example.test/codex/plugins/build") == []
    # The positive case — a bare vendor-prefixed branch name — is `test_the_gate_discriminates`'s
    # existing assertion, which this change must leave green; it is not repeated here because
    # this plan is walked by the gate and would trip on its own example.


@pytest.mark.parametrize("path", document_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_public_document_carries_a_source_repository_string(path: Path) -> None:
    assert offending(path.read_text(encoding="utf-8"), PUBLIC_FORBIDDEN) == [], path
