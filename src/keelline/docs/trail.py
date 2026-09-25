"""Regenerate the "Design and plan trail" listing inside the roadmap.

The roadmap's prose owns phase status; this listing makes the corpus navigable: every spec and
plan, grouped by theme, annotated with its delivery state. Delivered is the default; anything
else is declared in `trail.toml` beside the roadmap — that file is the one part a human
maintains, and it is the forward track in machine-readable form (Premise 9). A document
appearing for the first time has to declare its state, `delivered` included: a design is
written before the thing is built, so the first listing of one would otherwise assert that
unimplemented work has shipped.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from posixpath import relpath
from typing import TYPE_CHECKING, Any

from keelline.config.loader import toml_position
from keelline.config.paths import contained
from keelline.docs.hygiene import TRAIL_MARKER, TRAIL_MARKER_LINE, read_document
from keelline.errors import Failure
from keelline.findings import Finding
from keelline.gitenv import git_run

if TYPE_CHECKING:
    from keelline.config.schema import Config

# The marker and its anchored pattern are `docs.hygiene`'s, defined once: the budget reader cuts
# the roadmap's prose at the same line this module rebuilds from, and two spellings of one
# literal are two things that can disagree. Bound here for readability, not redefined.
MARKER = TRAIL_MARKER
END_MARKER = "<!-- end design and plan trail -->"
TRAIL_FILE = "trail.toml"
UNFILED = "Unfiled"
# The `trail` gate's two findings, which `docs trail --check` tells apart by rule.
ROADMAP_MISSING = "roadmap-missing"
TRAIL_STALE = "trail-stale"
DELIVERED = "delivered"
_ROW = re.compile(r"^- \[`([^`]+)`\]", re.MULTILINE)
# Every value this file interpolates into the listing has to survive being written into it
# verbatim. `rebuild` locates the block it replaces with `text.find(END_MARKER, …)`, so an end
# marker inside a `label` or a `state` splits the block there, and everything past the split
# falls outside the region the next run rewrites: three successive `keelline docs trail` runs
# grew the roadmap by its own height each time, `docs trail --check` became permanently stale
# with nothing an operator could do to satisfy it, and the prose the value carried after the
# marker settled into the roadmap — a document agents load, with no delimited region and no
# trust record behind it. A newline is the same defect one step earlier: it is what lets a value
# put a marker, or a heading, alone on a line, which is where `TRAIL_MARKER_LINE` and the budget
# reader's cut both look.
#
# There are two kinds of such value and they are caught in two places, because they arrive by two
# routes and their remedies differ. A `trail.toml` `label` or `state` is caught in `read_trail`,
# beside the type checks, because a `trail.toml` outside the contract must read as that file
# being wrong. A document's own FILENAME reaches the listing as both the row and the link,
# straight off `glob("*.md")` with no file to be outside a contract — and guarding only the
# first half left the defect whole: a tracked `…-a<!-- end design and plan trail -->b.md` grew
# the roadmap 18 → 22 → 26 lines over three runs, each exiting 0, with the end-marker count
# going 2 → 4 → 6, and `--check` stale forever. It is caught in `render_listing`, after the
# ignored and untracked documents are dropped, so a sibling session's oddly named local file
# cannot fail the command for everybody — the same reason `_untracked` exists.
_UNINTERPOLABLE = (
    "{path}: a {what} is written into the generated listing verbatim, so it must be a single "
    "line and must carry neither `{marker}` nor the end-of-trail comment"
)
# `{row!r}` is repository-authored text in a message, for `ledger.index.FOREIGN_CONTENT`'s
# reason: this reaches the terminal of the person who ran the command against their own
# repository, and naming the file is the whole of what makes "rename it" actionable. `!r` keeps
# a name holding a newline on one line.
_UNLISTABLE = (
    "{row!r} cannot be written into the {roadmap} listing: a document's name becomes both the "
    "row and the link verbatim, so it must be a single line and must carry neither `{marker}` "
    "nor the end-of-trail comment — rename the file"
)
_PREAMBLE = (
    "\n\nEvery design and plan document, grouped by theme and annotated with its\n"
    "delivery state. Regenerate with `keelline docs trail` after adding a document.\n"
    f"Delivered is the default; anything else is declared in `{TRAIL_FILE}` beside this\n"
    "file, which mirrors the forward track above.\n"
)


@dataclass(frozen=True)
class Trail:
    themes: tuple[tuple[str, re.Pattern[str]], ...]
    states: dict[str, str]


def trail_target(config: Config) -> str:
    """Where `trail.toml` sits for `config`, beside the roadmap, as a project-relative path.

    Only a location, read off `[paths] roadmap` without touching the disk: whether it may be read
    or written is `contained()`'s to say, which `trail_path` asks and the scaffold engine asks of
    every target it plans.
    """
    return str(PurePosixPath(config.paths.roadmap).parent / TRAIL_FILE)


def trail_path(root: Path, config: Config) -> Path:
    return contained(root, trail_target(config))


def _interpolable(value: str) -> bool:
    """Whether a repository-authored value may be written into the listing unchanged."""
    return "\n" not in value and MARKER not in value and END_MARKER not in value


def read_trail(path: Path) -> Trail:
    """`[[theme]]` tables in order (`label`, `pattern`) and a `[states]` table; absent is empty.
    Every value is repository-authored: a pattern is compiled under `re.error` → `Failure`."""
    if not path.is_file():
        return Trail((), {})
    try:
        raw: dict[str, Any] = tomllib.loads(read_document(path, path))
    except tomllib.TOMLDecodeError as exc:
        # Through `config.loader.toml_position`: `tomllib`'s message embeds the source for
        # several of its faults — a duplicate table is reported with the table's name in it —
        # and a TOML key is arbitrary quoted text. `trail.toml` is one of the twelve files
        # `keelline init` ships, so after this branch every repository `init` touches has one
        # that this function parses, which is what makes the leak newly reachable here.
        raise Failure(f"{path} is not valid TOML {toml_position(exc)}") from None
    themes: list[tuple[str, re.Pattern[str]]] = []
    # `[[theme]]` is an array of tables, so `theme` is a list — but the whole file is
    # repository-authored, and `theme = 1` would otherwise be iterated straight into a
    # `TypeError` the frame reports as an internal error (2). A project's malformed file must
    # read as their file being wrong, never as this tool being broken.
    declared = raw.get("theme", [])
    if not isinstance(declared, list):
        raise Failure(f"{path}: `theme` must be a list of [[theme]] tables")
    for entry in declared:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("label"), str)
            or not isinstance(entry.get("pattern"), str)
        ):
            raise Failure(f"{path}: every [[theme]] needs a string `label` and a string `pattern`")
        if not _interpolable(entry["label"]):
            raise Failure(
                _UNINTERPOLABLE.format(path=path, what="[[theme]] `label`", marker=MARKER)
            )
        try:
            themes.append((entry["label"], re.compile(entry["pattern"])))
        except re.error as exc:
            raise Failure(
                f"{path}: theme {entry['label']!r} has an invalid pattern: {exc}"
            ) from None
    states = raw.get("states", {})
    if not isinstance(states, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in states.items()
    ):
        raise Failure(f"{path}: [states] must map document rows to state strings")
    if not all(_interpolable(state) for state in states.values()):
        raise Failure(_UNINTERPOLABLE.format(path=path, what="[states] value", marker=MARKER))
    return Trail(tuple(themes), dict(states))


def theme_of(name: str, trail: Trail) -> str:
    for label, pattern in trail.themes:
        if pattern.search(name):
            return label
    return UNFILED


def _ignored(root: Path, paths: list[Path]) -> set[Path]:
    """Paths excluded by the repository's ignore rules alone.

    `--no-index` matters: `check-ignore` consults the index and answers "not ignored" for
    anything currently tracked, which would silently list a local-only document.

    `-z` matters for the same reason it does in `touched_plans`, and this is the one place the
    answer is matched back against the path that was asked about. Without it git C-quotes any
    path holding a non-ASCII byte or a space on OUTPUT — `docs/plans/2026-01-01-caf\303\251.md`
    comes back wrapped in quotes with the bytes escaped — so the answer never equals the path
    this function sent, an ignored document is read as "not ignored" and is listed in the
    roadmap, which is the exact case `--no-index` exists for. `-z` also makes the INPUT
    NUL-separated, so a path is never split on a byte of its own name either."""
    if not paths:
        return set()
    stdin = "\0".join(p.relative_to(root).as_posix() for p in paths)
    code, out = git_run(root, "check-ignore", "--no-index", "--stdin", "-z", stdin=stdin)
    # 1 simply means "nothing matched"; anything else is a tree git cannot speak for.
    if code not in (0, 1):
        return set()
    return {root / name for name in out.split("\0") if name}


def _untracked(root: Path, paths: list[Path]) -> set[Path]:
    """Documents git does not track yet, which the listing must not claim.

    CI checks out the tracked tree and computes the listing from that, so an untracked document
    makes a developer's `--check` disagree with CI over a file CI cannot see — routinely, since
    a sibling session's work-in-progress lands in the same directory. Skipping them keeps the
    two answers identical and matches what the listing is: a generated index OF THE REPOSITORY,
    not of one machine's disk. Falls back to "nothing untracked" where git cannot answer, so a
    non-git tree keeps working instead of silently emptying itself."""
    if not paths:
        return set()
    code, out = git_run(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
        "--",
        *(str(p.relative_to(root)) for p in paths),
    )
    if code != 0:
        return set()
    return {root / name for name in out.split("\0") if name}


def _documents(root: Path, config: Config) -> list[tuple[str, str, Path]]:
    """`(row, link, path)` per document: the row is `<dirname>/<file>`, the link is relative
    to the roadmap's own directory."""
    roadmap_dir = str(PurePosixPath(config.paths.roadmap).parent)
    found: list[tuple[str, str, Path]] = []
    for configured in (config.paths.specs, config.paths.plans):
        directory = contained(root, configured)
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            row = f"{PurePosixPath(configured).name}/{path.name}"
            found.append((row, relpath(f"{configured}/{path.name}", roadmap_dir), path))
    return found


def render_listing(root: Path, config: Config, trail: Trail) -> str:
    documents = _documents(root, config)
    paths = [path for _, _, path in documents]
    skip = _ignored(root, paths) | _untracked(root, paths)
    buckets: dict[str, list[tuple[str, str]]] = {}
    listed: set[str] = set()
    for row, link, path in documents:
        if path in skip:
            continue
        # Refused and not skipped: dropping the document would be the listing lying by silence,
        # which is the failure its other two guards exist to prevent, and the operator has a
        # remedy either way. The link is checked too — it is the same name, joined to the
        # configured `specs`/`plans` path, and that path is repository-authored as well.
        if not (_interpolable(row) and _interpolable(link)):
            raise Failure(_UNLISTABLE.format(row=row, roadmap=config.paths.roadmap, marker=MARKER))
        listed.add(row)
        buckets.setdefault(theme_of(path.name, trail), []).append((row, link))
    # A rename or deletion must not silently downgrade a state to the default. Without this, a
    # renamed design would reappear as `delivered` — asserting in the roadmap that unimplemented
    # work has shipped, which is the exact failure this listing exists to prevent, and `--check`
    # would stay green because the file is still self-consistent.
    stale = sorted(set(trail.states) - listed)
    if stale:
        raise Failure(
            f"{TRAIL_FILE} names documents that no longer exist (renamed, deleted, or now "
            "gitignored); update the map before regenerating: " + ", ".join(stale)
        )
    lines: list[str] = []
    total = pending = 0
    for label in [*(label for label, _ in trail.themes), UNFILED]:
        rows = buckets.get(label)
        if not rows:
            continue
        total += len(rows)
        lines.append(f"\n### {label} ({len(rows)})\n")
        # Sorted on the filename with its directory dropped, so a theme's designs and plans
        # interleave by date instead of splitting into two blocks.
        for row, link in sorted(rows, key=lambda r: r[0].split("/", 1)[1]):
            state = trail.states.get(row, DELIVERED)
            if state != DELIVERED:
                pending += 1
            lines.append(f"- [`{row}`]({link}) — {state}")
    lines.append(
        f"\n<!-- generated by keelline docs trail — {total} documents, "
        f"{pending} not plainly delivered -->"
    )
    lines.append(END_MARKER)
    return "\n".join(lines) + "\n"


def listed_paths(text: str) -> set[str]:
    """Document rows the trail listing in `text` names. Only the generator writes rows in this
    shape, so matching the whole file rather than the block is safe and stays tolerant of a
    block that cannot be located."""
    return set(_ROW.findall(text))


def undeclared_new_documents(before: str, after: str, trail: Trail) -> list[str]:
    """Documents the listing gains that never declared a state, so took the default.

    This is the mirror of the stale-key guard: that one catches a state whose document
    disappeared, this one catches a document that appeared with no state. Both end in the
    roadmap asserting that unimplemented work shipped — and this is the path taken every time
    somebody writes a design, not the rare rename.

    Nothing when `before` names no documents at all: that is a gutted or first-ever listing
    rather than a real addition, and treating the whole corpus as new would bury the signal and
    break regenerating a mangled block back into shape."""
    known = listed_paths(before)
    if not known:
        return []
    return sorted(row for row in listed_paths(after) - known if row not in trail.states)


def rebuild(text: str, root: Path, config: Config, trail: Trail) -> str:
    start = TRAIL_MARKER_LINE.search(text)
    if start is None:
        raise Failure(f"{config.paths.roadmap} is missing the '{MARKER}' heading")
    end = text.find(END_MARKER, start.end())
    if end == -1:
        raise Failure(f"{config.paths.roadmap} is missing the '{END_MARKER}' comment")
    head = text[: start.end()]
    # `tail` opens with the newline that followed the end marker, and `render_listing` already
    # supplies it. Stripping it keeps repeated runs byte-identical instead of growing a blank
    # line each time.
    tail = text[end + len(END_MARKER) :]
    return head + _PREAMBLE + render_listing(root, config, trail) + tail.lstrip("\n")


def trail_gate(root: Path, config: Config, base: str = "") -> list[Finding]:
    """The `trail` gate's whole composition: the roadmap's listing, as `rebuild` would write it.

    `docs trail --check` answers with this function. `base` is unread: every gate takes the same
    three arguments, so `keelline.assess.gates` holds each one as a value.
    """
    roadmap = contained(root, config.paths.roadmap)
    if not roadmap.is_file():
        return [Finding(ROADMAP_MISSING, config.paths.roadmap, None, "")]
    current = read_document(roadmap, config.paths.roadmap)
    if current == rebuild(current, root, config, read_trail(trail_path(root, config))):
        return []
    return [Finding(TRAIL_STALE, config.paths.roadmap, None, "")]
