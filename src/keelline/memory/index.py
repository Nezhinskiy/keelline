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
from dataclasses import dataclass, field
from pathlib import Path

from keelline.config.paths import PathEscape, contained
from keelline.config.schema import Config
from keelline.errors import Failure
from keelline.fsops import write_atomically
from keelline.memory.notes import UNRANKED, Note, Provenance, walk, with_index, write_note
from keelline.memory.store import Store, overlay_root, permitted_roots

INDEX_NAME = "MEMORY.md"
EXTRA_TITLE = "Elsewhere"
VOLATILE_SUFFIX = "volatile"
# Neither class may match a newline. `MEMORY.md`'s premise is that a *second, non-Keelline*
# writer appends entries here, so an unclosed `[` is an ordinary accident rather than an
# attack — and a title harvested across the line break is written straight into a note's
# one-line `index:` frontmatter, where the remainder spills out of the fence and the note
# stops parsing: silently quarantined out of the index, the standing rules and volatile
# injection, and in overlay mode synced to every machine.
_ENTRY = re.compile(r"^- \[([^\]\n]+)\]\(([^)\n]+)\)", re.MULTILINE)

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
    # The notes this run actually rewrote, empty when `write=False`. `trust.refresh_if_trusted`
    # needs to know which files Keelline itself authored, so that carrying trust across
    # `memory index` cannot also carry it across whatever else landed on disk (§9.4).
    written: list[Path] = field(default_factory=list)


def index_source(store: Store, config: Config, machine: Path | None) -> Path | None:
    """The index's own §9.1 target rule — the one `store._group_targets` applies to every
    configured group, applied here because nothing upstream applies it to `MEMORY.md`.

    `store.py` does not track the index as a group (it is not a `memory.groups` entry), so no
    per-link target check has ever reached it. Every reader of `store.path / INDEX_NAME` needs
    this same answer — `worktree.link`, which materialises it into a worktree, and
    `bundles._index`, which injects it into the model — so it lives here, beside `INDEX_NAME`,
    and is called rather than reimplemented.

    A missing or dangling index sources nothing. A real file sources itself, unconditionally.
    A symlink is the governed case: outside overlay mode it is refused outright (there is no
    overlay to validate it against, exactly like an ungoverned group symlink); in overlay mode
    it is honoured only when it resolves inside this project's own share of the recorded
    overlay (`permitted_roots`) — never a different project's.
    """
    target = store.path / INDEX_NAME
    if not target.exists():
        return None
    if not target.is_symlink():
        return target.resolve()
    if store.mode != "overlay":
        return None
    overlay = overlay_root(machine)
    if overlay is None:
        return None
    allowed = permitted_roots(overlay, config.project.name)
    resolved = target.resolve()
    if not any(resolved.is_relative_to(root.resolve()) for root in allowed):
        return None
    return resolved


def _appended(store: Store, config: Config, machine: Path | None) -> dict[str, str]:
    """What the second writer appended, from the file `index_source` says the index is.

    Harvesting goes through the same target rule as injection, and for the same reason turned
    around: `reconcile` writes what it finds here into each note's `index:` frontmatter, so an
    index symlinked at another project's share would persist that project's text into this
    one's notes — and in overlay mode from there onto every machine.
    """
    path = index_source(store, config, machine)
    if path is None or not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return {target: title for title, target in entries_in(text)}


def _relative(note: Note, store: Store) -> str:
    return f"{note.group_name}/{note.path.name}"


def reconcile(
    store: Store, config: Config, *, write: bool, machine: Path | None = None
) -> Reconciliation:
    """Give every note an `index:` line, harvesting the second writer's before inventing one.

    `config` rather than a bare group list: the groups came from it at every call site anyway,
    and the index's target rule needs `project.name` and — with `machine` — the recorded
    overlay, which a `Sequence[str]` cannot carry. Pass the same `machine` used to resolve
    `store`, exactly as `worktree.link` and `bundles.blocks` ask.
    """
    appended = _appended(store, config, machine)
    groups = config.memory.groups
    found = walk(store.path, [g for g in groups if g in store.groups])
    notes: list[Note] = []
    harvested: list[str] = []
    provisional: list[str] = []
    written: list[Path] = []
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
            written.append(note.path)
        notes.append(note)
    return Reconciliation(notes, harvested, provisional, found.unreadable, written)


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


def _extra(config: Config, store: Store) -> list[str]:
    """`memory.index_extra` entries that actually stay inside the project root.

    `config/paths.py` names this field, alongside `memory.groups`, as one its own guard does
    not cover, and assigns the check to "the lane that consumes them" in as many words. The
    strings are repository-controlled and land verbatim in `MEMORY.md`, which the `index`
    bundle injects — the same channel a symlinked index reaches. `contained` is called without
    `allow_final_symlink`, unlike `_group_targets`: a group legitimately *is* a symlink in
    overlay mode, while these are pointers to documents in the repository and a link at the
    last component escaping the root is the same escape as one halfway up.

    An entry that escapes is dropped, the way `_group_targets` drops a group whose target it
    refuses. Dropped silently, because `render_index` returns a string and has no report
    channel; `store.unavailable` is the shape that would carry one, and giving the index its
    own would change `Reconciliation` for every caller.
    """
    kept: list[str] = []
    for target in config.memory.index_extra:
        try:
            contained(store.root, target)
        except PathEscape:
            continue
        kept.append(target)
    return kept


def render_index(reconciled: Reconciliation, config: Config, store: Store) -> str:
    lines = [HEADER.rstrip("\n"), ""]
    by_group: dict[str, list[Note]] = {}
    for note in reconciled.notes:
        by_group.setdefault(note.group_name, []).append(note)
    for group in config.memory.groups:
        if by_group.get(group):
            lines += _section(group, by_group[group], store)
    extra = _extra(config, store)
    if extra:
        lines += [f"## {EXTRA_TITLE}", ""]
        lines += [f"- [{target}]({target})" for target in extra]
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
