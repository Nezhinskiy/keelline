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

from keelline.config.paths import contained
from keelline.docs.hygiene import TRAIL_MARKER, TRAIL_MARKER_LINE
from keelline.errors import Failure
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
DELIVERED = "delivered"
_ROW = re.compile(r"^- \[`([^`]+)`\]", re.MULTILINE)
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


def trail_path(root: Path, config: Config) -> Path:
    directory = PurePosixPath(config.paths.roadmap).parent
    return contained(root, str(directory / TRAIL_FILE))


def read_trail(path: Path) -> Trail:
    """`[[theme]]` tables in order (`label`, `pattern`) and a `[states]` table; absent is empty.
    Every value is repository-authored: a pattern is compiled under `re.error` → `Failure`."""
    if not path.is_file():
        return Trail((), {})
    try:
        raw: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise Failure(f"{path} is not valid TOML: {exc}") from None
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
    return Trail(tuple(themes), dict(states))


def theme_of(name: str, trail: Trail) -> str:
    for label, pattern in trail.themes:
        if pattern.search(name):
            return label
    return UNFILED


def _ignored(root: Path, paths: list[Path]) -> set[Path]:
    """Paths excluded by the repository's ignore rules alone.

    `--no-index` matters: `check-ignore` consults the index and answers "not ignored" for
    anything currently tracked, which would silently list a local-only document."""
    if not paths:
        return set()
    stdin = "\n".join(str(p.relative_to(root)) for p in paths)
    code, out = git_run(root, "check-ignore", "--no-index", "--stdin", stdin=stdin)
    # 1 simply means "nothing matched"; anything else is a tree git cannot speak for.
    if code not in (0, 1):
        return set()
    return {root / line for line in out.splitlines() if line}


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
