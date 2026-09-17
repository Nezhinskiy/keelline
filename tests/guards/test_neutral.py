"""§5.8: no project-identifying string in the public repository, held over this lane's files.

The design's whole-tree gate belongs to the `workflows` lane; this is the same rule scoped to
what the `guards` port can carry in, checked from the first task so a ported docstring cannot
land the state §11 requires it to shed.

**The denylist is stored as digests, not as the tokens themselves, and that is not decoration.**
A gate that lists the strings it is hiding publishes them: this file ships in a public
repository, so a plain-text list would put every identifier §5.8 forbids into the very tree the
rule is about, one `grep` away. Each entry is a lower-cased token's length and a short
`blake2s` digest of it; the scan hashes every window of each stored length and compares digests.
The behaviour is identical to the substring list it replaces — the same inputs fail — and a
digest is not a secret, it is merely not readable. **Do not "simplify" them back into
literals.** To add a token, run `digest_of("<token>")` and append `(len, digest)`.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LANE = (ROOT / "src" / "keelline" / "guards", ROOT / "tests" / "guards")
PLAN = "docs/plans/2026-09-15-guards.md"


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
# A documentation URL can carry a vendor name as a path segment, and none of the shapes below
# is a leak when it is part of one, so the shape scan reads the text with its URLs blanked out.
# The denylist scan does not: a forbidden token inside a URL is still that token.
_URL = re.compile(r"https?://\S+")
# Shapes a substring list cannot express: a personal address, a bare commit id, a
# vendor-prefixed branch name at any depth. Each arm is named so a hit says what it is.
SHAPES = (
    # Not `@users.noreply.github.com`: that is GitHub's generic form and a Task 5 negative.
    ("personal email", re.compile(r"@(?:gmail|yandex|mail|icloud|proton)\.\w+")),
    # At least one digit, so an eight-letter hex word (`deadbeef`) is not an id.
    ("bare commit id", re.compile(r"(?<![\w/])(?=[0-9a-f]*\d)[0-9a-f]{8,10}(?![\w/])")),
    # One arm for every form of the name, in three parts. The lookbehind keeps a dotted harness
    # directory out — a public document has to be able to name the one it configures. The
    # optional path prefix lets any depth in, so a remote-qualified name, a `refs/heads/` name,
    # a worktree path and a remote nobody thought to list are one shape rather than a list to
    # keep up with. And requiring a `-` or `_` in the branch segment is what tells a branch
    # name from the slashed prose pair of the two harness names, which this project's own
    # one-line pitch invites: real branch names are dashed by convention.
    (
        "vendor branch",
        re.compile(r"(?<![.\w])(?:[\w.-]+/)*(?:codex|claude|cursor)/[a-z0-9][\w-]*[-_][\w-]*"),
    ),
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
    lowered = _URL.sub(" ", text.lower())
    found.extend(name for name, shape in SHAPES if shape.search(lowered))
    return found


def lane_files() -> list[Path]:
    found = [path for directory in LANE for path in directory.rglob("*.py")]
    # The lane's non-Python artifacts are gated too; the whole-tree gate is `workflows`'.
    # The plan is one of them: it is the document the port's source literals were quoted from,
    # and a record nobody checks is how they come back. It is named without an existence guard
    # on purpose — a skipped file would hide exactly the drift this walk exists to catch.
    extras = [ROOT / PLAN]
    changelog = ROOT / "changelog.d" / "guards.feature.md"
    if changelog.is_file():
        extras.append(changelog)
    # `docs/cli.md` is deliberately not walked here: it is a shared, pre-existing file written
    # by other lanes, not this lane's ported state — `docs/cli.md:165` has `memory =
    # "docs/memory"` (a FORBIDDEN token) and `:192` has `.claude/settings.json` (hits the
    # `vendor branch` regex), both Keelline's own strings. Its guards sections are checked by
    # hand at Task 10.
    found.extend(extras)
    # This file carries no source token any more — the denylist is digests — but the regex arms
    # are proven below by fixtures that are personal-address-shaped and commit-id-shaped by
    # construction, so it stays the one file the gate does not read.
    return sorted(path for path in found if path.name != "test_neutral.py")


def test_the_gate_reads_something() -> None:
    # No mutation of its own: this is the mutation guard for the test below, which passes
    # vacuously if the walk ever finds no files. The plan is named because a walk that quietly
    # stopped covering it would look exactly like a walk that covers it and finds nothing.
    files = lane_files()
    assert any(path.name == "__init__.py" for path in files)
    assert ROOT / PLAN in files


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
    # `mutations.toml` is a shared file, so only this lane's entries are read: the ones whose
    # `file` names the guards package.
    text = (ROOT / "mutations.toml").read_text(encoding="utf-8")
    entries = [block for block in text.split("[[mutation]]") if "keelline/guards/" in block]
    for block in entries:
        assert offending(block) == [], block[:120]


@pytest.mark.parametrize("path", lane_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_lane_file_carries_a_source_repository_string(path: Path) -> None:
    assert offending(path.read_text(encoding="utf-8")) == [], path
