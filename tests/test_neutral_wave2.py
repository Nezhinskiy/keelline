"""§5.8: no project-identifying string in the public repository, held over this plan's files.

The design's whole-tree gate belongs to the `workflows` lane; this is the same rule scoped to
what the three wave-2 closure ports can carry in, checked from the first task so a ported
docstring, a ported skill or a ported theme list cannot land the state §11 requires it to
shed. It walks three areas, two document trees and four shared leaf modules because one plan
delivers them, and it lives at the top level of `tests/` for that reason.

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
PLAN = "docs/plans/2026-09-16-wave-2-closure-ledger-docs-skills.md"
FRAGMENTS = ("ledger", "docs-tooling", "skills-port", "memory-refs")
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
    ("vendor branch", re.compile(r"\b(?:codex|claude|cursor)/[a-z0-9][\w-]*")),
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


def lane_files() -> list[Path]:
    found: list[Path] = []
    for directory in LANE:
        found.extend(directory.rglob("*.py"))
        found.extend(directory.rglob("*.md"))
    found.extend(path for path in EXTRA_FILES if path.is_file())
    # The plan is named without an existence guard on purpose — a skipped file would hide
    # exactly the drift this walk exists to catch.
    found.append(ROOT / PLAN)
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
    assert ROOT / PLAN in files
    assert ROOT / "src" / "keelline" / "identifiers.py" in files
    assert ROOT / "src" / "keelline" / "findings.py" in files
    assert ROOT / "skills" / "close-bug" / "SKILL.md" in files


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
