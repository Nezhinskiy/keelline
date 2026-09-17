"""Write flat TOML tables, escaping every string, refusing everything it cannot represent.

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
capability record acquires a value nobody wrote; there are two callers and both know their own
types. Keys are held to the bare-key grammar for the same reason — quoting an unexpected key
would let `[project]` hold a name nobody chose to write.

Flat on purpose: `dumps` takes `{table: {key: value}}` and a dict in a value position is a
caller expecting a shape this does not emit. The one table named `""` is written before any
header, because the overlay's `projects/<name>/project.toml` holds its `remote` at the top
level — `memory.store._bound` reads it there, and moving it under a header would make this
serialiser and that reader disagree about one file.
"""

from __future__ import annotations

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
    raise Refusal(
        f"{where} holds a {type(value).__name__}, which this serialiser does not emit; it writes "
        f"strings, integers, booleans and lists of those, and refuses rather than guessing"
    )


def _value(value: object, where: str) -> str:
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_scalar(item, f"{where}[]") for item in value) + "]"
    return _scalar(value, where)


def dumps(tables: dict[str, dict[str, object]]) -> str:
    """`{table: {key: value}}` as TOML text, in the order given; `""` names the root table."""
    lines: list[str] = []
    for name, table in tables.items():
        if not isinstance(table, dict):
            raise Refusal(f"[{name}] is not a table; this serialiser writes flat tables only")
        if name:
            lines.append(f"[{_key(name, 'table name')}]")
        for key, value in table.items():
            lines.append(f"{_key(key, 'key')} = {_value(value, f'{name}.{key}')}")
        lines.append("")
    return "\n".join(lines)
