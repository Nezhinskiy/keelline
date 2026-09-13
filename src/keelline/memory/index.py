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
from keelline.errors import Failure, Refusal
from keelline.fsops import write_atomically
from keelline.memory.notes import UNRANKED, Note, Provenance, walk, with_index, write_note
from keelline.memory.store import Store, in_repository, overlay_root, permitted_roots

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
# The characters that end a markdown link early. A value carrying one of these is rendered
# into `- [title](target)` on both sides, so it does not merely look wrong: it puts whatever
# follows where `entries_in` reads the next field.
_LINK_SYNTAX = "])("


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
    # Notes that had a line waiting for them in the index and were not allowed to take it,
    # because the index is repository data and the note is not (`_harvestable`). They get a
    # provisional line from their own description instead, so they appear in `provisional` too;
    # this names the ones where that was a refusal rather than an absence, because a drop the
    # command cannot mention is a drop nobody reviews.
    refused_harvest: list[str] = field(default_factory=list)


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


def _appended(path: Path | None) -> dict[str, str]:
    """What the second writer appended, from the file `index_source` said the index is.

    Harvesting goes through the same target rule as injection, and for the same reason turned
    around: `reconcile` writes what it finds here into each note's `index:` frontmatter, so an
    index symlinked at another project's share would persist that project's text into this
    one's notes — and in overlay mode from there onto every machine.
    """
    if path is None or not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return {target: title for title, target in entries_in(text)}


def _harvestable(store: Store, source: Path | None, note: Note) -> bool:
    """Whether this note may take its `index:` line from the file `source` names.

    The target rule `_appended` applies guards one direction — an index symlinked into
    *another* project's overlay share. The inverse is the natural shape and was ungoverned: in
    overlay mode the index is legitimately a real file the clone shipped at `paths.memory`
    (`index_source`: "a real file sources itself, unconditionally") while the notes resolve out
    into the machine's own overlay. `reconcile(write=True)` then persisted repository-authored
    titles into `common/memory` — shared with *every project on the machine* and, per §6.2,
    synced across machines — from where another project whose index is the §6.3 symlink injects
    them raw, unwrapped, with no trust record anywhere in the chain.

    So the rule is one trust domain per harvest: **repository bytes do not become machine
    state.** A note that is itself repository data may take a repository index's line — nothing
    crosses — and a machine-owned index may supply anything, because those bytes are already
    the owner's.

    Deliberately not `trust.may_inject(..., repository_data=True)`, the review's other
    suggestion. A trust record says "this repository's memory may reach the model, as data". It
    does not say "this repository's memory may become my machine-level memory, unwrapped, in
    every other project". Those are different grants and only the first is the one the owner
    makes, so the gate here is the domain, not the record — which also means the ordinary
    same-domain cases keep working with no record at all, as they must: requiring one would
    stop `memory index` dead on a fresh in-repo store.
    """
    if source is None or not in_repository(store, source):
        return True
    return in_repository(store, note.path)


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
    source = index_source(store, config, machine)
    appended = _appended(source)
    groups = config.memory.groups
    found = walk(store.path, [g for g in groups if g in store.groups])
    notes: list[Note] = []
    harvested: list[str] = []
    provisional: list[str] = []
    written: list[Path] = []
    refused: list[str] = []
    for note in found.notes:
        if note.index:
            notes.append(note)
            continue
        line = appended.get(_relative(note, store))
        if line and not _harvestable(store, source, note):
            refused.append(note.name)
            line = None
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
    return Reconciliation(notes, harvested, provisional, found.unreadable, written, refused)


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

    **What is kept is the path `contained` returned, not the string that was checked.** The
    value was validated as a path and then consumed as text: `contained` answers about
    absoluteness, `..` and symlinks and says nothing about a value being one line, so a TOML
    multi-line string passed and was written verbatim into `MEMORY.md` — twice, as a link's
    title and as its target — carrying repository-authored prose through every index
    regeneration. Two guards close that. The value must be a single line, by `str.splitlines`
    rather than a scan for `\\n`, because `_split` in `notes.py` breaks on `\\x0b`, `\\x0c`,
    `\\x85`, U+2028 and U+2029 as well. And it may not hold `]`, `(` or `)`, the three
    characters that close a markdown link early and put the remainder where `entries_in` reads
    a *target* — the same channel the harvest writes back into a note's one-line `index:`.
    """
    kept: list[str] = []
    for target in config.memory.index_extra:
        if len(target.splitlines()) > 1 or any(char in target for char in _LINK_SYNTAX):
            continue
        try:
            resolved = contained(store.root, target)
        except PathEscape:
            continue
        kept.append(str(resolved.relative_to(store.root)))
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


def _destination(store: Store, config: Config, machine: Path | None) -> Path:
    """The one file the writer writes and the check compares against: what the readers source.

    `index_source` is the rule every *reader* applies — `bundles._index`, `_appended`,
    `worktree.link`. The writer did not apply it and neither did the check, and each half of
    that was its own defect. `write_atomically` ends in `os.replace`, which replaces the
    **link** rather than its target: one run stranded the overlay's shared copy on every other
    machine, turned the index into a real file inside the repository, and so flipped
    `in_repository` to True and closed the gate on the index bundle for good. `check_index`
    meanwhile read `store.path / INDEX_NAME` through `is_file()`, which follows the link, so
    `--check` answered about a file nothing injects: exit 0 and "index is current" while the
    index bundle produced `[]`.

    Both are the same question, so both ask it here, once.

    `None` from `index_source` has two causes and they are not the same answer. An index that
    is simply absent is the ordinary first run: the destination is the real path, and the check
    reports drift against nothing. An index that **is** a symlink and still sourced nothing was
    *refused* — outside overlay mode, or outside this project's share of the overlay — and
    writing there would clobber exactly the link §9.1 declined to honour. That is a `Refusal`
    (C5, exit 2) rather than a `Failure`: repository-controlled content reaching past a
    containment boundary is never a finding a caller may read as permission to continue.
    """
    source = index_source(store, config, machine)
    if source is not None:
        return source
    target = store.path / INDEX_NAME
    if target.is_symlink():
        raise Refusal(
            f"{target} is a symlink this store may not source ({INDEX_NAME} may link only "
            f"into this project's share of the recorded overlay, in overlay mode); refusing "
            f"to read or replace it"
        )
    return target


def check_index(
    store: Store, config: Config, reconciled: Reconciliation, *, machine: Path | None = None
) -> IndexCheck:
    """`machine` for the same reason `reconcile` takes one: without it this cannot call
    `index_source`, and a check that answers about a different file than the one harvested and
    injected is a green CI run over an empty bundle. Pass the value used to resolve `store`."""
    text = render_index(reconciled, config, store)
    path = _destination(store, config, machine)
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


def write_index(store: Store, config: Config, text: str, *, machine: Path | None = None) -> Path:
    """Write the index to the file the readers source, and return that file.

    Takes `config` and `machine` — a C3 contract change — because `_destination` cannot answer
    without them, and answering without them was the defect. The returned path is the file
    actually written, which in overlay mode is the shared copy in the overlay rather than the
    link inside the checkout; `trust.refresh_if_trusted` resolves both to the same file, so the
    record still covers the index it just wrote.
    """
    if not store.path.is_dir():
        raise Failure(f"{store.path} does not exist; the store was not created")
    path = _destination(store, config, machine)
    write_atomically(path, text)
    return path
