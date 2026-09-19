"""§5.8: no project-identifying string anywhere in the public repository — the whole tree.

Two lane-scoped copies of this gate held the door since wave 2, the second of them saying
"both gates are deleted the day the `workflows` lane ships the whole-tree gate — do not
extend either into a third." This is that day. Source under `src/`, `tests/` and `scripts/`
is held to the full table: a module has no reason to spell a default path. Every other
tracked text file is held to the public table, which exempts exactly the preset's own
default `[paths]` values, because a document that could not say where the note store lives
by default would be useless. The denylist is digests; the two docstrings this replaces say
why, and their reasoning is kept verbatim in `digest_of`.

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
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
THIS = Path(__file__).resolve()
FULL_TABLE_TREES = ("src", "tests", "scripts")
# How many tracked files the walk is allowed to skip for being undecodable. Zero, measured: this
# repository ships no binary. A file that changes it is a deliberate edit here and not a case
# that quietly stopped being checked.
UNDECODABLE = 0
# Only for the fallback walk in an unpacked sdist, where `git ls-files` cannot answer.
FALLBACK_EXCLUDED = {
    ".git",
    ".venv",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    ".claude",
    ".superpowers",
}


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
_URL = re.compile(r"https?://\S+")
# The arms that read the text with its URLs blanked out, and it is exactly one. A documentation
# URL can carry a vendor name as a path segment, so `/codex/quick-start` in a link is a path and
# not a branch. The other two arms read the original text, and that distinction is the whole
# point of naming them here rather than blanking once for everybody: a personal address inside a
# `mailto:`, a profile URL or a query parameter is still a personal address, and a commit id in
# a query parameter is still a commit id. Blanking the lot took both of those out of every URL
# in the tree — the same shape of defect as the arm this replacement was written for.
# The denylist scan is never blanked: a forbidden token inside a URL is still that token.
URL_BLIND = frozenset({"vendor branch"})
# Shapes a substring list cannot express: a personal address, a bare commit id, a
# vendor-prefixed branch name at any depth. Each arm is named so a hit says what it is.
SHAPES = (
    # Not `@users.noreply.github.com`: that is GitHub's generic form and a Task 5 negative.
    ("personal email", re.compile(r"@(?:gmail|yandex|mail|icloud|proton)\.\w+")),
    # At least one digit, so an eight-letter hex word (`deadbeef`) is not an id — and, by the
    # same argument in the other direction, at least one letter, so a plain decimal number is
    # not one either. The second lookahead is this gate's own finding: the first whole-tree
    # walk reddened `uv.lock` fifty-five times on `size = 13936739`, a file size the resolver
    # writes and no edit of ours can neutralise, and the arm would go on firing on every
    # byte count, timestamp and line number in the tree. What it costs is an abbreviated id
    # that happens to be all digits, which is (10/16)**8 of them and which no rule could tell
    # from an ordinary number anyway.
    (
        "bare commit id",
        re.compile(r"(?<![\w/])(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{8,10}(?![\w/])"),
    ),
    # One arm for every form of the name, in three parts, and the only one in `URL_BLIND`
    # above. The lookbehind keeps a dotted harness directory out — a public document has to be
    # able to name the one it configures. The optional path prefix lets any depth in, so a
    # remote-qualified name, a `refs/heads/` name, a worktree path and a remote nobody thought
    # to list are one shape rather than a list to keep up with. And requiring a `-` or `_` in
    # the branch segment is what tells a branch name from the slashed prose pair of the two
    # harness names, which this project's own one-line pitch invites: real branch names are
    # dashed by convention.
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
    lowered = text.lower()
    blanked = _URL.sub(" ", lowered)
    found.extend(
        name for name, shape in SHAPES if shape.search(blanked if name in URL_BLIND else lowered)
    )
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
# Three of the preset's eleven default `[paths]` values are also digest-table entries — the
# ones that were the source repository's paths before they were Keelline's defaults. Pinned so
# the exemption cannot quietly grow: a fourth would mean a token was added to the table for a
# path the plugin itself ships, which is a contradiction to resolve, not to exempt.
PRESET_PATHS_IN_TABLE = 3


def tracked_files() -> list[Path]:
    """Every file git tracks, or every file under the tree minus the fixed exclusions."""
    # `--others --exclude-standard` as well as `--cached`: a fixture added in this wave is
    # untracked until its commit, and a gate that could not see it until the commit after
    # would let the commit that adds it land unwalked. Step 2 says `git add -N` first.
    done = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=False,
    )
    if done.returncode == 0 and done.stdout:
        names = [n for n in done.stdout.decode("utf-8").split("\0") if n]
        return sorted(ROOT / n for n in names if (ROOT / n).is_file())
    # Anchored on the FIRST component: `tests/fixtures/hostile-project/.claude/settings.json`
    # is a fixture to walk, not a configuration directory to skip.
    return sorted(
        p
        for p in ROOT.rglob("*")
        if p.is_file() and p.relative_to(ROOT).parts[0] not in FALLBACK_EXCLUDED
    )


# **What the split gives up, stated as a decision rather than left as an accident.** The two
# gates this replaces walked `skills/**/*.md` and `agents/*.md` under the FULL table; DC10 says
# `.py` under the three source trees takes the full table and every other text file takes the
# public one, so under one gate those documents take the public table and may now spell a preset
# default `[paths]` value where they could not before. That is the design and not a slip: a skill
# is a document a person reads, and the argument that a README which could not say where the note
# store lives by default would be useless is the same argument one directory over. The denylist
# proper is unchanged for them — only the three exempted preset defaults move — and the shape arms
# are not table-scoped at all, so a personal address, a bare commit id and a vendor branch are
# still refused in a skill. Changing it back means changing DC10, not this function.
def table_for(path: Path) -> tuple[tuple[int, str], ...]:
    relative = path.relative_to(ROOT)
    source_tree = relative.parts[0] in FULL_TABLE_TREES
    if source_tree and (path.suffix == ".py" or relative.parts[0] == "scripts"):
        return FORBIDDEN
    return PUBLIC_FORBIDDEN


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def test_the_gate_reads_the_whole_tree() -> None:
    # The non-vacuity guard for the parametrised walk below. Named files from six different
    # trees, and a floor well under today's count (310 when this was written; the commit says
    # so), so a walk that stopped at one directory cannot pass.
    files = tracked_files()
    names = {str(p.relative_to(ROOT)) for p in files}
    # No `.github/` name here: that tree is outside `source-include`, and this floor has to
    # hold in the unpacked sdist the fallback walk exists for.
    for wanted in (
        "README.md",
        "src/keelline/cli.py",
        "docs/cli.md",
        "mutations.toml",
        "hooks/run-hook.sh",
        "scripts/keelline",
        "tests/test_fsops.py",
    ):
        assert wanted in names, wanted
    assert len(files) >= 200, len(files)
    assert THIS in files
    # And that a file was actually READ. Every parametrised case below calls `_text` and skips
    # on `None`, so a regression in `_text` — a changed encoding argument, a widened `except` —
    # turns all of them into skips and the gate reports green over a tree that could name
    # anything. Measured when this was written: 335 tracked files, none undecodable, so the skip
    # arm is taken by nothing at all and `UNDECODABLE` is a number to move deliberately when a
    # binary file is added rather than a silence to walk past.
    readable = [path for path in files if path != THIS and _text(path) is not None]
    assert len(readable) >= 200, len(readable)
    assert len(files) - 1 - len(readable) == UNDECODABLE, (len(files), len(readable))


def test_the_two_tables_are_told_apart_by_the_file_they_are_for() -> None:
    # `table_for` is what decides whether a file may name a default path, so it is worth an
    # assertion of its own rather than only being exercised through the walk. A module and a
    # test module take the full table; the preset that ships those defaults, every document,
    # and a data file under a full-table tree take the public one. `scripts/keelline` has no
    # suffix at all and is source, which is why the tree name is a second arm.
    assert table_for(ROOT / "src" / "keelline" / "cli.py") == FORBIDDEN
    assert table_for(ROOT / "tests" / "test_fsops.py") == FORBIDDEN
    assert table_for(ROOT / "scripts" / "keelline") == FORBIDDEN
    assert table_for(ROOT / "src" / "keelline" / "presets" / "recommended.toml") == PUBLIC_FORBIDDEN
    fixture = ROOT / "tests" / "fixtures" / "smoke-project" / "keelline.toml"
    assert table_for(fixture) == PUBLIC_FORBIDDEN
    assert table_for(ROOT / "docs" / "cli.md") == PUBLIC_FORBIDDEN
    assert table_for(ROOT / "README.md") == PUBLIC_FORBIDDEN
    # And the two tables really are different tables, or every arm above would be the same
    # claim written seven ways.
    assert PUBLIC_FORBIDDEN != FORBIDDEN


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
    # Inside a URL, which is where a personal address and a commit id are most often written:
    # a `mailto:`, a profile link, a query parameter. Only the vendor arm is blanked, because
    # only the vendor arm has a legitimate reason to appear in a URL path; blanking for all
    # three took these two out of every link in the tree and nothing said so.
    assert offending("https://example.test/u?mail=someone@gmail.com") == ["personal email"]
    assert offending("https://example.test/r?sha=1b279648") == ["bare commit id"]
    assert offending("cut from codex/inbound-remediation") == ["vendor branch"]
    # Every prefixed form, on one arm rather than on a list of remote names: this is how a
    # commit message, `git branch -a`, a `refs/` ref and a worktree path each write the same
    # branch. `wp/` is this repository's own branch prefix and `myremote` is a remote nobody
    # thought to list, which is the point — two rounds of review found this arm short by
    # exactly the prefixes no one had enumerated.
    branch = ["vendor branch"]
    assert offending("cut from origin/codex/inbound-remediation") == branch
    assert offending("remotes/origin/codex/inbound-remediation") == branch
    assert offending("refs/heads/codex/inbound-remediation") == branch
    assert offending("wp/codex/inbound-remediation") == branch
    assert offending("myremote/codex/inbound-remediation") == branch
    assert offending("../wt/codex/foo-bar") == branch
    assert offending("upstream/claude/some-branch") == branch
    assert offending("merged fork/cursor/spike-one") == branch
    assert offending("cat secrets/.env; person@example.com; 0x1234; deadbeef") == []
    assert offending("Co-authored-by: Someone <someone@users.noreply.github.com>") == []
    # A decimal number is not a commit id, and this is the assertion the whole-tree walk
    # bought: `uv.lock` writes `size = 13936739` fifty-five times, the resolver rewrites it on
    # every lock, and the arm that read it as an id could only ever have been answered by
    # exempting a file from the gate. Eight digits, ten digits, and the same run with one hex
    # letter in it, which is an id again.
    assert offending("size = 13936739") == []
    assert offending("bytes: 1234567890") == []
    assert offending("bytes: 123456789a") == ["bare commit id"]


def test_mutations_toml_carries_no_source_repository_string() -> None:
    # `mutations.toml` is walked whole under the public table by the parametrised test below,
    # like every other tracked document. This is the stricter half the two lane gates each
    # carried for their own entries: a mutation quotes a line of the file it names, so the
    # entry is held to *that file's* table. Scoping it by the named file rather than by a
    # hand-kept list of path prefixes is what one gate can do that two could not — neither
    # copy could see the other's lane, and every lane added since was nobody's.
    entries = tomllib.loads((ROOT / "mutations.toml").read_text(encoding="utf-8"))["mutation"]
    assert len(entries) >= 200, len(entries)
    for entry in entries:
        quoted = "\n".join(str(entry[key]) for key in ("name", "file", "before", "after"))
        assert offending(quoted, table_for(ROOT / str(entry["file"]))) == [], entry["name"]


def test_the_exemption_is_exactly_the_presets_default_paths() -> None:
    # Reddens if the preset stops shipping a default path (the exemption shrinks and a public
    # document that names it reddens too), or if someone rewrites `PUBLIC_FORBIDDEN` by hand.
    exempt = set(FORBIDDEN) - set(PUBLIC_FORBIDDEN)
    assert len(exempt) == PRESET_PATHS_IN_TABLE
    # `exempt <= set(_preset_paths())` used to stand here and was dropped: `PUBLIC_FORBIDDEN`
    # is *defined* as that difference, so the subset held for any derivation and reddened for
    # none. The size is the claim with teeth — it is the one a hand-written table breaks.
    # The full table's size is pinned by `test_the_denylist_is_stored_as_digests`; the source
    # walk still refuses those three, which `test_the_public_table_still_discriminates` shows.


def test_the_public_table_still_discriminates() -> None:
    # A preset path is allowed by the public table and refused by the full one; a planted
    # token is refused by both; the dotted harness directory is not a vendor branch.
    from keelline.presets import load_preset

    defaults = load_preset("recommended")["defaults"]["paths"].values()
    exempt_value = next(
        value for value in defaults if (len(value), digest_of(value)) in set(FORBIDDEN)
    )
    assert offending(exempt_value, PUBLIC_FORBIDDEN) == []
    assert offending(exempt_value) != []
    # Over every default, not over `next(iter(...))`: which value that picked depended on TOML
    # key order, and it landed on one in neither table, where the assertion held for any
    # derivation at all. Over the whole set, `PUBLIC_FORBIDDEN = FORBIDDEN` reddens it.
    assert all(offending(value, PUBLIC_FORBIDDEN) == [] for value in defaults)
    probe = "quernstone"
    planted = ((len(probe), digest_of(probe)),)
    assert offending("see quernstone", planted) == [f"token {digest_of(probe)}"]
    assert offending("edit .claude/settings.json and .codex/hooks.json") == []
    assert offending("~/.claude/settings.json") == []
    # The dot in the lookbehind, which the dash requirement does not make redundant: those two
    # files are cleared by having no dash in the segment after the slash, but a *dashed* name
    # directly under a dotted harness directory would read as a branch without it.
    assert offending("the .codex/hook-config.toml file") == []
    assert offending("see https://example.test/codex/plugins/build") == []
    # And the URL blanking, which is likewise the only thing standing between the gate and a
    # documentation URL whose path segment happens to be dashed — the commonest shape there is.
    assert offending("see https://example.test/codex/quick-start") == []
    # A remote name inside a URL path is still a path segment, and a remote name on its own is
    # not a branch.
    assert offending("see https://example.test/origin/codex/plugins/build") == []
    assert offending("push to origin/main and upstream/dev") == []
    # The slashed prose pair. This project's own one-line pitch names the two harnesses that
    # way, so the pair is the natural phrasing in every document this table walks; an arm that
    # forbade it would be a trap laid for the next writer rather than a gate.
    assert offending("the Claude/Codex split") == []
    assert offending("claude/codex parity") == []
    assert offending("a claude/agents directory") == []
    # The positive case — a bare vendor-prefixed branch name — is `test_the_gate_discriminates`'s
    # existing assertion, which this change must leave green; it is not repeated here because
    # this plan is walked by the gate and would trip on its own example.


# This file is the one the walk does not read, and the exclusion is `!= THIS` rather than a name
# so a rename cannot quietly drop a different file. It carries no denylist token — the table is
# digests — but the three shape arms are proven by fixtures that are personal-address-shaped,
# commit-id-shaped and branch-shaped **by construction**, which is the same reason the two gates
# this replaces each skipped themselves. The pre-commit sweep reads the raw diff and so reports
# those fixtures; a shape hit on a line of this module is the gate quoting itself, and the stop
# condition Global Constraints states is a `token` hit.
@pytest.mark.parametrize(
    "path",
    [p for p in tracked_files() if p != THIS],
    ids=lambda p: str(p.relative_to(ROOT)),
)
def test_no_tracked_file_carries_a_project_identifying_string(path: Path) -> None:
    text = _text(path)
    if text is None:
        pytest.skip("binary")
    assert offending(text, table_for(path)) == [], path
