"""One note, read and written without losing what this reader does not understand (§9.2).

The store has two writers: the harness's native memory writer and Keelline. That is workable
only because neither rewrites the other's keys — and "does not rewrite" has to mean *bytes*,
not *meaning*. A reader that parses `description: 'tis a note` and renders it back as
`description: "'tis a note"` has changed a file it was asked to leave alone; do that to
seventy notes and the first `memory index` is a diff nobody can review, followed by a
ping-pong with the native writer over quoting.

So the frontmatter is kept as the lines it arrived as, and `render_note` rewrites **only the
keys whose value this run actually changed**. Byte-identity for an untouched note is then a
property of the design rather than a property of the quoting rules, and D5's
bit-compatibility requirement holds for keys this module has never heard of.

A YAML library would be the obvious parser and is not available: the runtime is stdlib-only
so that a hook works before any environment exists. The grammar below is the smallest one the
real corpus needs — flat `key: value`, plus exactly one two-space block under `metadata:` —
and it refuses anything else loudly, with a line number, rather than guessing.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from keelline.errors import Failure
from keelline.fsops import write_atomically

# Sort sentinel for a note whose `startup` metadata could not be parsed as an int (D7: this
# is not a budget or cap read from config, and no shipped file needs to change if it does —
# it only needs to sort after every real startup rank the corpus can hold).
UNRANKED = 10_000
FENCE = "---"
_KEY = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z_][A-Za-z0-9_]*):(?P<rest>.*)$")
_NOT_A_RULE = frozenset({"false", "no", "off"})
DECLARED = ("name", "description", "index", "index_provenance", "group", "group_order")


class NoteError(Failure):
    """A note whose frontmatter cannot be read without guessing."""


class NoteType(StrEnum):
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"


class Provenance(StrEnum):
    CURATED = "curated"
    NATIVE = "native"
    PROVISIONAL = "provisional"


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _quote(value: str) -> str:
    """Only ever applied to a value this run is writing for the first time."""
    if value and not any(ch in value for ch in ":#\"'") and value.strip() == value:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _parse_int(value: str | None) -> int | None:
    """`group_order` parsed the way `startup`/`as_of` already are: a value that is not an
    int is `None`, never a crash. `"--5".lstrip("-").isdigit()` is `True` while `int("--5")`
    still raises, and `walk` only catches `NoteError` — a bare `ValueError` here would cost
    the whole store walk, which is exactly what this module exists to not do.
    """
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class Note:
    path: Path
    name: str
    description: str
    body: str
    index: str | None = None
    index_provenance: Provenance = Provenance.CURATED
    group: str | None = None
    group_order: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    # The frontmatter exactly as it was read, and the values parsed out of it. `render_note`
    # rewrites a line only where the two disagree, so an unchanged note round-trips byte for
    # byte and a key this module does not model is never touched.
    raw: tuple[str, ...] = ()
    original: dict[str, str] = field(default_factory=dict)

    @property
    def type(self) -> NoteType | None:
        try:
            return NoteType(self.metadata.get("type", ""))
        except ValueError:
            return None

    @property
    def startup(self) -> int | None:
        raw = self.metadata.get("startup")
        if raw is None or raw.strip().lower() in _NOT_A_RULE:
            return None
        try:
            return int(raw)
        except ValueError:
            return UNRANKED

    @property
    def as_of(self) -> date | None:
        raw = self.metadata.get("as_of")
        if not raw:
            return None
        try:
            return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None

    @property
    def words(self) -> int:
        return len(self.body.split())

    @property
    def group_name(self) -> str:
        """The store group a note belongs to: its folder, always. `group` is a sub-heading."""
        return self.path.parent.name


def _split(text: str, path: Path) -> tuple[list[str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != FENCE:
        raise NoteError(f"{path}: no frontmatter; a note opens with '---'")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == FENCE)
    except StopIteration:
        raise NoteError(f"{path}: frontmatter is never closed") from None
    body = "\n".join(lines[end + 1 :]).strip("\n")
    return lines[1:end], body


def _parse(lines: list[str], path: Path) -> tuple[dict[str, str], dict[str, str]]:
    top: dict[str, str] = {}
    meta: dict[str, str] = {}
    in_metadata = False
    for offset, line in enumerate(lines, start=2):
        if not line.strip():
            continue
        match = _KEY.match(line)
        if match is None:
            raise NoteError(f"{path}: line {offset} is not 'key: value'")
        indent, key, rest = match.group("indent"), match.group("key"), match.group("rest")
        value = rest.strip()
        if indent == "":
            if key == "metadata":
                if value:
                    raise NoteError(f"{path}: line {offset}: metadata must open a block")
                in_metadata = True
                continue
            in_metadata = False
            if not value:
                raise NoteError(f"{path}: line {offset}: {key!r} has no value on its own line")
            if key in top:
                raise NoteError(f"{path}: line {offset}: duplicate key {key!r}")
            top[key] = _unquote(value)
            continue
        if not in_metadata or len(indent) != 2:
            raise NoteError(f"{path}: line {offset}: only 'metadata:' may nest, two spaces deep")
        if key in meta:
            raise NoteError(f"{path}: line {offset}: duplicate key 'metadata.{key}'")
        meta[key] = _unquote(value)
    return top, meta


def read_note(path: Path) -> Note:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise NoteError(f"{path} cannot be read: {exc}") from exc
    lines, body = _split(text, path)
    top, meta = _parse(lines, path)
    try:
        provenance = Provenance(top.get("index_provenance", Provenance.CURATED))
    except ValueError as exc:
        raise NoteError(f"{path}: {exc}") from exc
    return Note(
        path=path,
        name=top.get("name", path.stem),
        description=top.get("description", ""),
        body=body,
        index=top.get("index"),
        index_provenance=provenance,
        group=top.get("group"),
        group_order=_parse_int(top.get("group_order")),
        metadata=meta,
        raw=tuple(lines),
        original=dict(top),
    )


def _wanted(note: Note) -> dict[str, str | None]:
    """The declared keys this module owns, as they should read after this run."""
    return {
        "name": note.name,
        "description": note.description,
        "index": note.index,
        "index_provenance": (
            None if note.index_provenance is Provenance.CURATED else note.index_provenance.value
        ),
        "group": note.group,
        "group_order": None if note.group_order is None else str(note.group_order),
    }


def _still_the_read_time_default(key: str, value: str | None, note: Note) -> bool:
    """True when a declared key absent from the file carries only the harmless default
    `read_note` fills in for convenience (`""` for `description`, the file stem for `name`)
    rather than a value this run actually decided to write. Writing it in would invent a
    line the file never had — the exact defect a real note without `description:` exposed.
    """
    if key in note.original:
        return False
    if key == "description":
        return value == ""
    if key == "name":
        return value == note.path.stem
    return False


def render_note(note: Note) -> str:
    wanted = _wanted(note)
    # A key this module could not parse — `group_order: 2b` — has a wanted value of `None`
    # while the file plainly has a line. That is not a deletion, it is a value this reader
    # does not understand, and nothing in this lane deletes a declared key, so an absent
    # wanted value never overrides a present original.
    changed = {
        key: value
        for key, value in wanted.items()
        if value != note.original.get(key)
        and not (value is None and key in note.original)
        and not _still_the_read_time_default(key, value, note)
    }
    lines: list[str] = [FENCE]
    seen: set[str] = set()
    for line in note.raw:
        match = _KEY.match(line)
        key = match.group("key") if match and match.group("indent") == "" else None
        if key is None or key not in changed:
            lines.append(line)
            continue
        seen.add(key)
        value = changed[key]
        if value is not None:
            lines.append(f"{key}: {_quote(value)}")
    # A key this run introduced goes in declared order, before `metadata:`.
    fresh = [k for k in DECLARED if k in changed and k not in seen and changed[k] is not None]
    if fresh:
        cut = next(
            (i for i, line in enumerate(lines) if line.strip() == "metadata:"),
            len(lines),
        )
        insert = [f"{key}: {_quote(str(changed[key]))}" for key in fresh]
        lines = lines[:cut] + insert + lines[cut:]
    lines.append(FENCE)
    return "\n".join(lines) + "\n\n" + note.body + "\n"


def with_index(note: Note, line: str, provenance: Provenance) -> Note:
    return replace(note, index=line, index_provenance=provenance)


def write_note(note: Note) -> None:
    write_atomically(note.path, render_note(note))


@dataclass(frozen=True)
class Walk:
    """Notes that parsed, and the files that did not — never one at the cost of the other."""

    notes: list[Note]
    unreadable: list[tuple[Path, str]]


def walk(store: Path, groups: Sequence[str]) -> Walk:
    """Every `*.md` note under the named groups, quarantining the files that will not parse.

    §9.2 says non-note files are "ignored … and flagged by `doctor`", and a store is a place
    humans put things: one superseded design document with no frontmatter must not cost the
    whole store, which is exactly what a raising walk does inside a handler's `except`.
    """
    found: list[Note] = []
    unreadable: list[tuple[Path, str]] = []
    for group in groups:
        directory = store / group
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name.startswith((".", "_")):
                continue
            try:
                found.append(read_note(path))
            except NoteError as exc:
                unreadable.append((path, str(exc)))
    return Walk(notes=found, unreadable=unreadable)
