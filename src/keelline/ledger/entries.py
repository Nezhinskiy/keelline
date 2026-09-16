"""The bug ledger: one file per bug under `[paths] bugs`, one generated index.

The index is generated from the entry files and must never be edited by hand: the entry files
are the truth, the index carries nothing of its own, so a conflict in it is always resolved by
regenerating rather than by merging text.

Frontmatter is a deliberately flat subset of YAML — `key: value` lines, an inline `[a, b]`
list, no nesting — so this module reads it with the standard library alone. Anything outside
the subset raises `LedgerError` rather than parsing to a default: a bug report that silently
loses its status is worse than one that fails the guard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from keelline.config.paths import contained
from keelline.errors import Failure
from keelline.identifiers import Identifiers, identifiers

if TYPE_CHECKING:
    from keelline.config.schema import Config

STATUSES = ("open", "partial", "fixed", "rejected", "void")
SEVERITIES = ("high", "medium", "low")
KEYS = ("id", "title", "status", "severity", "area", "found", "source", "fixed_in", "related")
REQUIRED_KEYS = ("id", "title", "status", "found")
# `void` records a number that was allocated and never carried a bug, so it has no severity
# and no area to record.
REQUIRED_UNLESS_VOID = ("severity", "area")

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n\n?(.*)\Z", re.DOTALL)
_KEY_VALUE = re.compile(r"\A([a-z_]+):[ \t]*(.*)\Z")
_ISO_DATE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")
# A value that would parse as something other than a plain string in real YAML. The subset
# stays valid YAML, so anything ambiguous is rejected rather than guessed at — which means the
# leading character class has to be YAML's whole indicator set, not the part of it this ledger
# happened to hit. A `--source` of `#412 in the tracker` written bare is the shape that proved
# it: this module's own reader hands the string back, and `yaml.safe_load` reads the value as a
# comment and the key as null, so the promise at the top of this file quietly stops holding.
# A value that *ends* in a colon is the same promise broken at the other end — `source: a:` is
# a nested mapping to a real YAML reader — so it is quoted too.
_NEEDS_QUOTING = re.compile(r"\A[-?:,\[\]{}#&*!|>'\"%@`]|: | #|:\Z")


class LedgerError(Failure):
    """A ledger file that cannot be read, or a rule that has been broken.

    A `Failure`, so the exit code 1 it carries is the frame's to map, never this module's
    (C5: library modules raise, only `cli.py` maps).
    """


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    status: str
    severity: str
    area: str
    found: str
    source: str
    fixed_in: str
    related: tuple[str, ...]
    body: str
    path: Path

    @property
    def number(self) -> int:
        # `parse_entry` validated the identifier against `ids.exact`, so the digits are known
        # to be there and no pattern is needed to read them back.
        return int(self.id.rsplit("-", 1)[1])


def _unquote(raw: str, *, key: str, where: Path) -> str:
    """Return the string a frontmatter value denotes, or raise."""
    if not raw.startswith('"'):
        if _NEEDS_QUOTING.search(raw):
            raise LedgerError(f"{where}: `{key}` needs double quotes around {raw!r}")
        return raw.strip()
    if len(raw) < 2 or not raw.endswith('"'):
        raise LedgerError(f"{where}: `{key}` has an unterminated quoted value")
    body = raw[1 : len(raw) - 1]
    # The final `"` closes the value only when the backslash run before it is even, since `\\`
    # is itself an escape. Testing the last two characters instead rejects this tool's own
    # output: `quote` writes a title ending in `\` as `"…\\"`, and one such title in the
    # source's ledger aborted a whole migration through its renderer and this reader.
    if (len(body) - len(body.rstrip("\\"))) % 2:
        raise LedgerError(f"{where}: `{key}` has an unterminated quoted value")
    out: list[str] = []
    index = 0
    while index < len(body):
        character = body[index]
        if character != "\\":
            out.append(character)
            index += 1
            continue
        following = body[index + 1 : index + 2]
        if following not in ('"', "\\"):
            raise LedgerError(f"{where}: `{key}` uses an unsupported escape `\\{following}`")
        out.append(following)
        index += 2
    return "".join(out)


def _require_iso_date(value: str, *, where: Path) -> str:
    """`value` back, once it is a date that exists.

    Both halves are needed. `date.fromisoformat` alone accepts the compact `YYYYMMDD` form and
    the ISO week form (`2026-W33-1`), neither of which the index's Found column or any date
    comparison here is written for, so
    the shape test keeps the extended form. The shape test alone accepts `2026-02-30` and
    `2026-13-45` — digits in the right places, days nobody can have found a bug on — in the one
    field this guard is meant to be the authority on.
    """
    if not _ISO_DATE.match(value):
        raise LedgerError(f"{where}: `found` must be an ISO date (YYYY-MM-DD), got {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise LedgerError(
            f"{where}: `found` names a date that does not exist: {value!r}"
        ) from error
    return value


def _parse_related(raw: str, *, where: Path, ids: Identifiers) -> tuple[str, ...]:
    if not raw:
        return ()
    if not (raw.startswith("[") and raw.endswith("]")):
        raise LedgerError(
            f"{where}: `related` must be an inline list like `[{ids.shape}, {ids.shape}]`"
        )
    items = [item.strip() for item in raw[1:-1].split(",") if item.strip()]
    for item in items:
        if not ids.is_identifier(item):
            raise LedgerError(
                f"{where}: `related` names {item!r}, which is not a {ids.prefix} identifier"
            )
    return tuple(items)


def parse_entry(text: str, *, path: Path, ids: Identifiers) -> Entry:
    """Parse one entry file's text, raising `LedgerError` on anything ambiguous.

    `path` is never opened here — it names the file in every message this raises, and becomes
    the parsed entry's own `path`. So callers pass the form they want an operator to read: a
    repo-relative one, since these messages are printed by `check` on CI, where an absolute
    path is a runner's scratch directory nobody can act on.
    """
    match = _FRONTMATTER.match(text)
    if match is None:
        raise LedgerError(f"{path}: no `---` frontmatter block at the top of the file")
    fields: dict[str, str] = {}
    for number, line in enumerate(match.group(1).splitlines(), start=2):
        if not line.strip():
            continue
        if line[:1] in (" ", "\t"):
            raise LedgerError(f"{path}:{number}: nested frontmatter is not supported")
        key_value = _KEY_VALUE.match(line)
        if key_value is None:
            raise LedgerError(f"{path}:{number}: expected `key: value`, got {line!r}")
        key, raw = key_value.group(1), key_value.group(2).strip()
        if key not in KEYS:
            raise LedgerError(f"{path}:{number}: unknown frontmatter key `{key}`")
        if key in fields:
            raise LedgerError(f"{path}:{number}: duplicate key `{key}`")
        fields[key] = raw

    for key in REQUIRED_KEYS:
        if not fields.get(key):
            raise LedgerError(f"{path}: missing required frontmatter key `{key}`")
    identifier = _unquote(fields["id"], key="id", where=path)
    if not ids.is_identifier(identifier):
        raise LedgerError(f"{path}: `id` must look like {ids.shape}, got {identifier!r}")
    status = _unquote(fields["status"], key="status", where=path)
    if status not in STATUSES:
        raise LedgerError(f"{path}: `status` must be one of {', '.join(STATUSES)}, got {status!r}")
    if status != "void":
        for key in REQUIRED_UNLESS_VOID:
            if not fields.get(key):
                raise LedgerError(f"{path}: missing required frontmatter key `{key}`")
    severity = _unquote(fields.get("severity", ""), key="severity", where=path)
    if severity and severity not in SEVERITIES:
        raise LedgerError(
            f"{path}: `severity` must be one of {', '.join(SEVERITIES)}, got {severity!r}"
        )
    found = _require_iso_date(_unquote(fields["found"], key="found", where=path), where=path)

    return Entry(
        id=identifier,
        title=_unquote(fields["title"], key="title", where=path),
        status=status,
        severity=severity,
        area=_unquote(fields.get("area", ""), key="area", where=path),
        found=found,
        source=_unquote(fields.get("source", ""), key="source", where=path),
        fixed_in=_unquote(fields.get("fixed_in", ""), key="fixed_in", where=path),
        related=_parse_related(fields.get("related", ""), where=path, ids=ids),
        body=match.group(2),
        path=path,
    )


def bugs_dir(root: Path, config: Config) -> Path:
    return contained(root, config.paths.bugs)


def load_entries(root: Path, config: Config) -> list[Entry]:
    """Every entry under the configured ledger directory, ordered by identifier number.

    Parsed against the repo-relative path, which is `parse_entry`'s documented contract.
    Handing it the absolute one made the writing commands describe a malformed entry by a
    path under a temporary directory while `check` described the same file repo-relatively —
    and on CI the absolute form names a runner's scratch directory nobody can act on.
    """
    ids = identifiers(config)
    directory = bugs_dir(root, config)
    entries = [
        parse_entry(path.read_text(encoding="utf-8"), path=path.relative_to(root), ids=ids)
        for path in sorted(directory.glob(f"{ids.prefix}-*.md"))
    ]
    return sorted(entries, key=lambda entry: entry.number)


def quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def scalar(value: str) -> str:
    """A frontmatter value written so `_unquote` gives back this exact string.

    Every writer goes through here rather than deciding per field: a `fixed_in` of a
    backticked short commit id is the commonest value in a ledger and, unquoted, is the
    leading backtick `_NEEDS_QUOTING` refuses.
    """
    return quote(value) if _NEEDS_QUOTING.search(value) else value


def field_line(key: str, value: str) -> str:
    """`key: value`, or a bare `key:` when there is no value.

    A trailing space on an empty field is whitespace an editor may strip on save, and an entry
    file that no longer matches what the writer produced is one a later reader reports as a
    conflicting duplicate against the tool's own output.
    """
    written = scalar(value)
    return f"{key}: {written}" if written else f"{key}:"


def related_field(related: tuple[str, ...] | list[str]) -> str:
    """The `related:` line, which `field_line` cannot write.

    Its quote decision would wrap the leading `[` and turn the inline list into a string. Both
    writers needed the exception and each carried its own copy of this line, with a comment
    pointing at the other as justification — which is the argument for a third helper, not for
    a second copy. They have to stay byte-identical: a writer that compares an existing entry
    file against a rendered one reports any difference as a conflicting duplicate, so two
    spellings of this line would make the tool conflict with its own writes.
    """
    return f"related: [{', '.join(related)}]" if related else "related:"
