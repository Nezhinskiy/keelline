"""The index is a rendering, not a file anyone edits (D6, §9.3).

Two machines editing one hand-written index is the most contended file in the store; a
generated one is resolved by regeneration. The curation does not disappear, it moves into each
note's `index:` line — and because a second writer appends its own lines to the index, the
generator harvests those before it renders, so nothing a session wrote is lost.

Sections come from `[memory] groups`, one per folder, and a note's `group` is rendered as a
sub-heading *inside* its folder's section. Read literally, §9.2's "the folder is the default"
would put a `group` value into the section list, which no configuration declares; this is the
reading that keeps both sentences true.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from keelline.config.schema import Config
from keelline.errors import Failure
from keelline.fsops import write_atomically
from keelline.memory.notes import UNRANKED, Note, Provenance, walk, with_index, write_note
from keelline.memory.store import Store

INDEX_NAME = "MEMORY.md"
EXTRA_TITLE = "Elsewhere"
VOLATILE_SUFFIX = "volatile"
_ENTRY = re.compile(r"^- \[([^\]]+)\]\(([^)]+)\)", re.MULTILINE)

HEADER = (
    "# Memory Index\n\n"
    "> Routing table. Every entry is a pointer, never the answer: when its trigger fires,\n"
    "> open the note.\n"
)
VOLATILE_LEAD = "Injected in full at session start; these links are for citation and pruning."


def entries_in(text: str) -> list[tuple[str, str]]:
    return _ENTRY.findall(text)


def section_title(group: str) -> str:
    head, *rest = group.split("-")
    return " — ".join([head.capitalize(), *rest])


def is_volatile(group: str) -> bool:
    """Derived from the configured group name, not from one hardcoded string."""
    return group.endswith(VOLATILE_SUFFIX)


@dataclass(frozen=True)
class Reconciliation:
    notes: list[Note]
    harvested: list[str]
    provisional: list[str]
    unreadable: list[tuple[Path, str]]


def _appended(store: Store) -> dict[str, str]:
    path = store.path / INDEX_NAME
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return {target: title for title, target in entries_in(text)}


def _relative(note: Note, store: Store) -> str:
    return f"{note.group_name}/{note.path.name}"


def reconcile(store: Store, groups: Sequence[str], *, write: bool) -> Reconciliation:
    appended = _appended(store)
    found = walk(store.path, [g for g in groups if g in store.groups])
    notes: list[Note] = []
    harvested: list[str] = []
    provisional: list[str] = []
    for note in found.notes:
        if note.index:
            notes.append(note)
            continue
        line = appended.get(_relative(note, store))
        if line:
            note = with_index(note, line, Provenance.NATIVE)
            harvested.append(note.name)
        else:
            note = with_index(note, note.description, Provenance.PROVISIONAL)
            provisional.append(note.name)
        if write:
            write_note(note)
        notes.append(note)
    return Reconciliation(notes, harvested, provisional, found.unreadable)


def _order(note: Note) -> tuple[int, int, str]:
    rank = note.startup
    return (
        UNRANKED if rank is None else rank,
        UNRANKED if note.group_order is None else note.group_order,
        note.name,
    )


def _entry(note: Note, store: Store) -> str:
    return f"- [{note.index}]({_relative(note, store)})"


def _section(group: str, notes: list[Note], store: Store) -> list[str]:
    lines = [f"## {section_title(group)}", ""]
    if is_volatile(group):
        lines += [VOLATILE_LEAD, ""]
    ungrouped = sorted((n for n in notes if not n.group), key=_order)
    lines += [_entry(note, store) for note in ungrouped]
    if ungrouped:
        lines.append("")
    # Grouped notes are collected by their `group` sub-heading first, then each heading is
    # emitted once. Interleaving `_order` across two sub-headings (Alpha, Beta, Alpha, ...)
    # must not split one heading's members apart or reopen it — every member of a heading has
    # to be gathered before that heading is ever written out.
    by_heading: dict[str, list[Note]] = {}
    for note in notes:
        if note.group:
            by_heading.setdefault(note.group, []).append(note)
    for heading in sorted(by_heading, key=lambda h: min(_order(n) for n in by_heading[h])):
        lines += [f"### {heading}", ""]
        lines += [_entry(note, store) for note in sorted(by_heading[heading], key=_order)]
    if by_heading:
        lines.append("")
    return lines


def render_index(reconciled: Reconciliation, config: Config, store: Store) -> str:
    lines = [HEADER.rstrip("\n"), ""]
    by_group: dict[str, list[Note]] = {}
    for note in reconciled.notes:
        by_group.setdefault(note.group_name, []).append(note)
    for group in config.memory.groups:
        if by_group.get(group):
            lines += _section(group, by_group[group], store)
    if config.memory.index_extra:
        lines += [f"## {EXTRA_TITLE}", ""]
        lines += [f"- [{target}]({target})" for target in config.memory.index_extra]
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


@dataclass(frozen=True)
class IndexCheck:
    drifted: bool
    words: int
    lines: int
    bytes_: int
    over_budget: bool
    over_caps: list[str]
    provisional: list[str]
    unreadable: list[str]


def check_index(store: Store, config: Config, reconciled: Reconciliation) -> IndexCheck:
    text = render_index(reconciled, config, store)
    path = store.path / INDEX_NAME
    current = path.read_text(encoding="utf-8") if path.is_file() else None
    caps = []
    if len(text.splitlines()) > config.native_caps.memory_index_lines:
        caps.append("memory_index_lines")
    if len(text.encode("utf-8")) > config.native_caps.memory_index_bytes:
        caps.append("memory_index_bytes")
    return IndexCheck(
        drifted=current != text,
        words=len(text.split()),
        lines=len(text.splitlines()),
        bytes_=len(text.encode("utf-8")),
        over_budget=len(text.split()) > config.budgets.effective("memory_index_words"),
        over_caps=caps,
        provisional=list(reconciled.provisional),
        unreadable=[str(path) for path, _ in reconciled.unreadable],
    )


def write_index(store: Store, text: str) -> Path:
    path = store.path / INDEX_NAME
    if not path.parent.is_dir():
        raise Failure(f"{path.parent} does not exist; the store was not created")
    write_atomically(path, text)
    return path
