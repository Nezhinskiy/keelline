"""Write TOML tables, escaping every string, refusing everything it cannot represent.

One serialiser and not one per lane. `attach` writes the overlay's `projects/<name>/project.toml`
and `setup` writes the machine configuration; hand-rolled, that is two writers in two waves with
no edge between them and no escaping rule — and the value this was written for is a **git remote
URL**, which the Global Constraints list among repository-authored bytes. A URL carrying a quote
and a newline closes its own string and writes further keys into a record that decides what
`attach` trusts.

A leaf module: it imports `keelline.errors` and nothing else, so either caller reaches it
without paying for an area.

One rule, stated as the module's whole contract: every string is emitted as a basic TOML string
with `"`, `\\` and the control characters escaped, and a value this cannot represent raises
rather than being mangled. Silently dropping an unexpected type, or `str()`-ing it, is how a
capability record acquires a value nobody wrote. Keys are held to the bare-key grammar for the
same reason — quoting an unexpected key would let `[project]` hold a name nobody chose to write.

**Anything `tomllib` can parse, this can emit.** That is a wider contract than the first draft's
("two callers and both know their own types"), and a third input made it necessary: `setup`
rewrites `~/.config/keelline/config.toml`, a file `README.md` documents the owner as writing by
hand. The document read back off that file is not a caller's own dict — it is whatever a person
wrote — and refusing a type merely because no caller of ours produces it wedged the command
permanently: `[personal] scale = 1.5` or `[personal.editor] name = "nvim"` made every future
`keelline setup` exit 2 naming a serialiser the owner has never heard of. So floats, the four
TOML date and time types, and nested tables are emitted; what is left refused is what no TOML
document could have held, which is a caller bug and still worth refusing.

`dumps` takes `{table: {key: value}}`, and a dict in a value position becomes a sub-table
header (`[personal.editor]`, after the parent's own keys, which is the order TOML requires). A
dict *inside a list* becomes an inline table, because an array of tables has no header form
that survives being nested in a value. The one table named `""` is written before any header,
because the overlay's `projects/<name>/project.toml` holds its `remote` at the top level —
`memory.store._bound` reads it there, and moving it under a header would make this serialiser
and that reader disagree about one file.

**Comments are not preserved, and cannot be**: `tomllib` discards them on the way in, so a
rewrite of a hand-edited file keeps every table, key and value and loses the prose around them.
`setup.machine`'s docstring says the same thing where the owner's file is actually rewritten.
"""

from __future__ import annotations

import datetime
import re

from keelline.errors import Refusal

BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def _key(name: object, what: str) -> str:
    if not isinstance(name, str) or not BARE_KEY.match(name):
        raise Refusal(
            f"{what} {name!r} is not a bare TOML key matching {BARE_KEY.pattern}; a caller that "
            f"means to write one writes one, and quoting it here would record a name nobody chose"
        )
    return name


def _string(value: str) -> str:
    out = []
    for char in value:
        if char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif char < "\x20" or char == "\x7f":
            # Every other C0 control and DEL. Legal in a basic string only as an escape, so a
            # raw one is a parse error rather than a mangled value — which is worse, not better.
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def _scalar(value: object, where: str) -> str:
    # `bool` before `int`, because `isinstance(True, int)` is True and `1` is not `true`.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # `repr` spells the three special values the way TOML does (`inf`, `-inf`, `nan`) and
        # gives a round-tripping decimal, always with a point or an exponent, for the rest.
        return repr(value)
    # `datetime` before `date`, because a `datetime` is a `date`; both spell themselves the way
    # TOML spells an offset date-time, a local date-time, a local date and a local time.
    if isinstance(value, datetime.datetime | datetime.date | datetime.time):
        return value.isoformat()
    raise Refusal(
        f"{where} holds a {type(value).__name__}, which this serialiser does not emit; it writes "
        f"every type a TOML document can hold — strings, integers, floats, booleans, dates and "
        f"times, tables, and lists of those — and refuses anything else rather than guessing"
    )


def _inline(table: dict[str, object], where: str) -> str:
    """A dict in a list position, as an inline table: `{ a = 1 }`.

    An array of tables (`[[x]]`) parses back as a list of dicts, and a header form cannot be
    nested inside a value, so the inline spelling is the one shape that round-trips.
    """
    body = ", ".join(
        f"{_key(key, 'key')} = {_value(value, f'{where}.{key}')}" for key, value in table.items()
    )
    return "{" + body + "}"


def _value(value: object, where: str) -> str:
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_element(item, f"{where}[]") for item in value) + "]"
    return _scalar(value, where)


def _element(value: object, where: str) -> str:
    if isinstance(value, dict):
        return _inline(value, where)
    return _value(value, where)


def _emit(lines: list[str], path: tuple[str, ...], table: dict[str, object]) -> None:
    """One table's own keys, then one sub-table per dict value — the order TOML requires."""
    header = ".".join(_key(part, "table name") for part in path)
    if header:
        lines.append(f"[{header}]")
    children: list[tuple[str, dict[str, object]]] = []
    for key, value in table.items():
        if isinstance(value, dict):
            children.append((_key(key, "key"), value))
            continue
        lines.append(f"{_key(key, 'key')} = {_value(value, f'{header}.{key}')}")
    lines.append("")
    for key, child in children:
        _emit(lines, (*path, key), child)


def dumps(tables: dict[str, dict[str, object]]) -> str:
    """`{table: {key: value}}` as TOML text, in the order given; `""` names the root table."""
    lines: list[str] = []
    for name, table in tables.items():
        if not isinstance(table, dict):
            raise Refusal(f"[{name}] is not a table; this serialiser writes tables of keys")
        _emit(lines, (name,) if name else (), table)
    return "\n".join(lines)
