"""Every ledger violation under a root, most structural first, as `Finding`s."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from keelline.errors import Failure, Refusal
from keelline.findings import Finding
from keelline.gitenv import NO_ANSWER, git_run
from keelline.identifiers import identifiers
from keelline.ledger.entries import (
    Entry,
    LedgerError,
    bugs_dir,
    parse_entry,
    read_ledger_text,
)
from keelline.ledger.index import (
    ENTRIES_MISSING,
    FOREIGN_CONTENT,
    foreign_index_lines,
    index_text,
    is_generated_index,
    render_index,
)
from keelline.ledger.scan import code_mentions, entry_citations

if TYPE_CHECKING:
    from pathlib import Path

    from keelline.config.schema import Config


EVIDENCE_LABEL = "**What this evidence does not establish:**"
# The template writes this after the label; a `high` entry with the placeholder untouched has
# not filled the line in. One constant feeds both the template and the rule so they cannot
# drift apart.
EVIDENCE_PLACEHOLDER = "the reading a later plan must not inherit"
# The negative lookahead is the point: the scaffold writes this line with its own placeholder
# text, so a bare match on the label would let every freshly filed entry satisfy the rule
# without anyone having written a word — a placeholder that satisfies its own check is the
# failure mode this rule exists to prevent.
# `[^\S\n]*` (same-line whitespace) and not `\s*`: the latter crosses newlines under MULTILINE
# and would let a bare label pass as long as anything followed it anywhere later in the body.
_EVIDENCE_BOUNDARY = re.compile(
    rf"^{re.escape(EVIDENCE_LABEL)}[^\S\n]*(?!{re.escape(EVIDENCE_PLACEHOLDER)})\S", re.MULTILINE
)
_CONFLICT_MARKER = re.compile(r"^(<{7} |={7}$|>{7} )", re.MULTILINE)
_BODY_STATE_BULLET = re.compile(r"^- \*\*(Status|Severity):\*\*", re.MULTILINE)
LEDGER_REMOVED = (
    "a commit this change forked from the base at carries the ledger ({bugs} or {index}) and "
    "this tree has neither; deleting the ledger does not switch the bugs gate off: restore it "
    "from the base"
)
ENTRY_REMOVED = (
    "a commit this change forked from the base at carries this entry and this tree does not; "
    "ledger entries are never deleted: restore it from the base, and move one with `keelline "
    "bugs renumber`, which leaves a `void` entry at the old number"
)
_BASE_UNREAD = (
    "git could not find the commits HEAD forked from `{base}` at, or list {bugs} and {index} "
    "there, under {root} ({cause}), so whether this change deleted the ledger or an entry of it "
    "is unknown and the bugs gate proved nothing. In CI the cause is a checkout too shallow to "
    "hold the base ref (`fetch-depth: 0`); locally it is a `--base` that names a ref this clone "
    "does not have, or one that shares no history with HEAD"
)
_SHALLOW = "this clone is shallow, so the commits HEAD forked from may be cut off"


@dataclass(frozen=True)
class _BaseLedger:
    carried: bool  # the fork point has the ledger directory or the index
    entries: tuple[str, ...]  # the entry files directly under the directory there, by name


def uninitialised(root: Path, config: Config) -> bool:
    """No ledger yet: no ledger directory *and* no index this tool generated. The second half
    is the point — the directory missing on its own also describes a ledger whose entry files
    were deleted under a generated index that still links every one of them. Only citations
    are checked here, so the gate can be registered before the first entry."""
    return not bugs_dir(root, config).is_dir() and not is_generated_index(index_text(root, config))


def _base_ledger(root: Path, config: Config, base: str) -> _BaseLedger:
    """What the commits HEAD forked from `base` at carry of the ledger: whether any has the
    directory or the index, and the `<PREFIX>-nnn.md` entry files directly under the directory
    in any of them.

    Those commits are `git merge-base --all <base> HEAD`, every best common ancestor: where
    `plan` reads `<base>...HEAD`, git picks one of them. What the base gained after the change
    forked is not the change's to have kept, so a branch behind its base is not blamed for an
    entry filed since; and what the change forked with, it still answers for, on a stale branch
    as on the merge commit CI checks out, whose base parent the base can have moved past. A
    history the change shapes itself can give it several merge bases, and the one `merge-base`
    alone answers, the newest by date, can predate an entry another of them carries: a merge
    deletes that entry all the same. So each is listed with one `git ls-tree -r` of the two
    configured paths, whose names come back relative to `root`, and their entries are united.
    Entries are append-only, so the union refuses no branch that deleted nothing.

    A base shaped like an option is refused, as `plan check` refuses it. A base git cannot list,
    one that shares no commit with HEAD, and any base in a shallow clone, where the commits HEAD
    forked from can be cut off and the merge base git sees be an older one, are a `Failure` —
    "could not run" to a gate — and never "the base has no ledger", which would pass exactly the
    change this question exists to catch.
    """
    if base.startswith("-"):
        raise Refusal(f"{base!r} looks like an option, not a base ref")
    bugs, index = config.paths.bugs, config.paths.bug_index
    code, out = git_run(root, "rev-parse", "--is-shallow-repository")
    if code == 0 and out.strip() == "true":
        raise Failure(
            _BASE_UNREAD.format(bugs=bugs, index=index, base=base, root=root, cause=_SHALLOW)
        )
    code, out = git_run(root, "merge-base", "--all", base, "HEAD")
    forks = out.split() if code == 0 else []
    found: set[str] = set()
    for fork in forks:
        code, out = git_run(root, "ls-tree", "-r", "-z", "--name-only", fork, "--", bugs, index)
        if code != 0:
            break
        found.update(name for name in out.split("\0") if name)
    if code != 0 or not forks:
        cause = NO_ANSWER if code < 0 else f"git exited {code}"
        raise Failure(
            _BASE_UNREAD.format(bugs=bugs, index=index, base=base, root=root, cause=cause)
        )
    names = sorted(found)
    ids = identifiers(config)
    under = f"{bugs}/"
    entries = tuple(
        name.removeprefix(under)
        for name in names
        if name.startswith(under)
        and name.endswith(".md")
        and ids.is_identifier(name.removeprefix(under).removesuffix(".md"))
    )
    return _BaseLedger(bool(names), entries)


def _removed_entries(root: Path, config: Config, base: _BaseLedger | None) -> list[Finding]:
    """Every entry file `base` carries whose exact name this tree's ledger directory does not
    hold, one finding each.

    Entries are append-only: `bugs renumber` leaves a `void` entry at the number it moves from,
    so no command this project ships deletes one, and a change that does is refused whatever
    still mentions the identifier. The mentions cannot decide it, and nor can the fixtures
    marker, which is an exemption a file grants itself.

    The names are compared with the directory's own listing, never looked up one by one: a
    filesystem that folds case finds `BR-001.md` at `br-001.md`, which the ledger, loading its
    entries by exact name, does not, so a rename in case alone passed there and failed on Linux.
    A directory that is not there, or cannot be listed, holds no entry.
    """
    if base is None:
        return []
    try:
        present = set(os.listdir(bugs_dir(root, config)))
    except OSError:
        present = set()
    return [
        Finding("entry-removed", f"{config.paths.bugs}/{name}", None, ENTRY_REMOVED)
        for name in base.entries
        if name not in present
    ]


def _dangling_mentions(root: Path, config: Config, known: set[str]) -> list[Finding]:
    """Every identifier the scanned files mention that `known` does not hold, one finding per
    identifier at its first mention."""
    found: list[Finding] = []
    for identifier, locations in sorted(code_mentions(root, config).items()):
        if identifier not in known:
            path_, line = locations[0]
            found.append(
                Finding(
                    "dangling-mention",
                    path_.as_posix(),
                    line,
                    f"mentions {identifier}, which has no entry file "
                    f"(referenced {len(locations)} time(s))",
                )
            )
    return found


def _unledgered(root: Path, config: Config, base: _BaseLedger | None) -> list[Finding]:
    """The findings for a tree with no ledger: the ledger the change forked with, when it
    forked with one, and every mention and citation of an entry, since with no ledger each one
    dangles.

    "No ledger" is read off the tree, which a pull request writes, so the tree's word for it
    cannot be what switches the gate off: the commits the change forked from the base at are
    asked whether it had one, and a mention of an identifier is as much a reference as a
    citation of its file. A project that registers the gate before its first entry has no
    ledger there and mentions none, and stays green, as does a branch forked before the base's
    first entry. With no `base` — `bugs check` run without `--base` — only the tree is judged.
    The one `ledger-removed` finding stands for every entry that commit carried.
    """
    found: list[Finding] = []
    if base is not None and base.carried:
        bugs, index = config.paths.bugs, config.paths.bug_index
        found.append(
            Finding("ledger-removed", bugs, None, LEDGER_REMOVED.format(bugs=bugs, index=index))
        )
    empty: set[str] = set()
    found.extend(_dangling_mentions(root, config, empty))
    return found + _dangling_citations(root, config, empty)


def _dangling_citations(root: Path, config: Config, known: set[str]) -> list[Finding]:
    """Every entry file a document or source cites that `known` does not hold, one finding per
    identifier at its first citation."""
    found: list[Finding] = []
    for identifier, locations in sorted(entry_citations(root, config).items()):
        if identifier not in known:
            path_, line = locations[0]
            found.append(
                Finding(
                    "dangling-citation",
                    path_.as_posix(),
                    line,
                    f"cites {config.paths.bugs}/{identifier}.md, which does not exist "
                    f"(referenced {len(locations)} time(s))",
                )
            )
    return found


def problems(root: Path, config: Config, base: str = "") -> list[Finding]:
    """Every ledger violation under `root`, most structural first.

    Before the ledger directory exists *and* before this tool has written an index there is
    nothing it owns, which is what lets the check be registered in CI one change before the
    first entry is filed: only a reference to an entry is reported then, since with no ledger
    every one of them dangles, and, against a `base`, a ledger the change forked with
    (`_unledgered`). A generated index with no ledger directory behind it is the other thing
    that shape describes, and it is the ledger having been deleted. Against a `base`, every arm
    past that one also names each entry the change forked with and the tree lacks
    (`entry-removed`). Both are read at every commit HEAD forked from `base` at
    (`_base_ledger`).
    """
    carried = _base_ledger(root, config, base) if base else None
    if uninitialised(root, config):
        return _unledgered(root, config, carried)
    ids = identifiers(config)
    bugs = bugs_dir(root, config)
    index_name = config.paths.bug_index
    # First: a deleted entry is the most structural finding a ledger can have.
    found = _removed_entries(root, config, carried)
    if not bugs.is_dir():
        missing = ENTRIES_MISSING.format(bugs=config.paths.bugs, index=index_name)
        return [Finding("entries-missing", index_name, None, missing), *found]

    entries: list[Entry] = []
    required = set(config.ledger.evidence_boundary_required_for)
    for path in sorted(bugs.glob(f"{ids.prefix}-*.md")):
        # Parsed against the repo-relative path, which is the one every message here names:
        # these are printed by CI, where an absolute path is a runner's scratch directory.
        relative = path.relative_to(root).as_posix()
        try:
            text = read_ledger_text(path, where=path.relative_to(root))
        except LedgerError as error:
            found.append(Finding("unreadable-entry", relative, None, str(error)))
            continue
        if _CONFLICT_MARKER.search(text):
            found.append(Finding("conflict-marker", relative, None, "unresolved conflict marker"))
            continue
        try:
            entry = parse_entry(text, path=path.relative_to(root), ids=ids)
        except LedgerError as error:
            found.append(Finding("unreadable-entry", relative, None, str(error)))
            continue
        if entry.id != path.stem:
            found.append(
                Finding(
                    "id-mismatch", relative, None, f"`id` {entry.id} does not match its filename"
                )
            )
        if _BODY_STATE_BULLET.search(entry.body):
            found.append(
                Finding(
                    "state-in-body",
                    relative,
                    None,
                    "body restates `**Status:**`/`**Severity:**`; those live in the "
                    "frontmatter alone",
                )
            )
        if entry.severity in required and not _EVIDENCE_BOUNDARY.search(entry.body):
            found.append(
                Finding(
                    "evidence-boundary",
                    relative,
                    None,
                    f"severity `{entry.severity}` needs a filled `{EVIDENCE_LABEL}` line — a "
                    "plan built on this entry inherits its silences as premises",
                )
            )
        entries.append(entry)

    known = {entry.id for entry in entries}
    by_id: defaultdict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        by_id[entry.id].append(entry)
    for identifier, holders in sorted(by_id.items()):
        if len(holders) > 1:
            joined = ", ".join(str(h.path) for h in holders)
            found.append(
                Finding(
                    "duplicate-id",
                    "",
                    None,
                    f"{identifier} is claimed by more than one file: {joined}",
                )
            )
    for entry in entries:
        for identifier in entry.related:
            if identifier not in known:
                found.append(
                    Finding(
                        "dangling-related",
                        entry.path.as_posix(),
                        None,
                        f"`related` names {identifier}, which has no entry file",
                    )
                )

    current = index_text(root, config)
    foreign = foreign_index_lines(root, current, config)
    if foreign:
        found.append(
            Finding(
                "foreign-index-content",
                index_name,
                None,
                FOREIGN_CONTENT.format(index=index_name, count=len(foreign), first=foreign[0]),
            )
        )
    # Suppressed while the index holds foreign content: regenerating is what deletes it, so
    # recommending it here would hand the operator the destructive step.
    elif current != render_index(sorted(entries, key=lambda e: e.number), config):
        found.append(Finding("stale-index", index_name, None, "is stale; run: keelline bugs index"))

    found.extend(_dangling_mentions(root, config, known))
    # Wider than the scan above, and reported separately because a citation says something a
    # bare mention does not: it names a path, so a reader who follows it gets a 404 rather than
    # an unfamiliar identifier. Closing an entry and renaming its file is the shape that leaves
    # one behind, and it lands in a docs-only commit.
    return found + _dangling_citations(root, config, known)


def bugs_gate(root: Path, config: Config, base: str = "") -> list[Finding]:
    """The `bugs` gate's whole composition: every ledger violation, before there is a ledger
    every reference to an entry, and against the base a ledger or an entry the change forked
    with that the tree lacks.

    `bugs check` answers with this function, with `--base` as `base` or `""`, which judges the
    tree alone; every gate run passes the base it judges against.
    """
    return problems(root, config, base)
