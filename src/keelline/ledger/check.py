"""Every ledger violation under a root, most structural first, as `Finding`s."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

from keelline.findings import Finding
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


def uninitialised(root: Path, config: Config) -> bool:
    """No ledger yet: no ledger directory *and* no index this tool generated. The second half
    is the point — the directory missing on its own also describes a ledger whose entry files
    were deleted under a generated index that still links every one of them. `bugs check` is
    inert here (exit 0), which is what lets the gate be registered before the first entry."""
    return not bugs_dir(root, config).is_dir() and not is_generated_index(index_text(root, config))


def problems(root: Path, config: Config) -> list[Finding]:
    """Every ledger violation under `root`, most structural first.

    Returns an empty list before the ledger directory exists *and* before this tool has
    written an index — there is nothing it owns, which is what lets the check be registered in
    CI one change before the first entry is filed. A generated index with no ledger directory
    behind it is the other thing that shape describes, and it is the ledger having been
    deleted.
    """
    found: list[Finding] = []
    if uninitialised(root, config):
        return found
    ids = identifiers(config)
    bugs = bugs_dir(root, config)
    index_name = config.paths.bug_index
    if not bugs.is_dir():
        return [
            Finding(
                "entries-missing",
                index_name,
                None,
                ENTRIES_MISSING.format(bugs=config.paths.bugs, index=index_name),
            )
        ]

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
    # Wider than the scan above, and reported separately because a citation says something a
    # bare mention does not: it names a path, so a reader who follows it gets a 404 rather than
    # an unfamiliar identifier. Closing an entry and renaming its file is the shape that leaves
    # one behind, and it lands in a docs-only commit.
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


def bugs_gate(root: Path, config: Config, base: str = "") -> list[Finding]:
    """The `bugs` gate's whole composition: every ledger violation, `[]` before there is a ledger.

    `bugs check` answers with this function after its own inert arm. `base` is unread: every
    gate takes the same three arguments, so `keelline.assess.gates` holds each one as a value.
    """
    return problems(root, config)
