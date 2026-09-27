"""The two bounds on a repository-chosen name: `printable` withholds it, `quoted` escapes it."""

from __future__ import annotations

import ast

import pytest

from keelline.printed import UNPRINTABLE, printable, quoted
from tests.crafted import CRAFTED

# Names the path grammar admits: each prints as itself under both bounds, so ordinary output is
# unchanged by either.
INSIDE = ["docs/a.md", "BR-001.md", ".hidden", "..foo", "a_b/c-d.e"]
# Names outside it, one per way out. `x\udce9` is how Linux hands Python a file name whose bytes
# are not UTF-8 (a lone surrogate), so it is covered here portably, where the filesystem cases
# that need such a name skip on APFS. `café.md`, `My Note.md` and `заметки.md` are ordinary names
# the grammar still refuses: it is ASCII-only on purpose, and those print as the stand-in.
OUTSIDE = [
    "",
    ".",
    "..",
    "a/../b",
    "a//b",
    "a/",
    "-rf",
    "a\rb",
    "a\u009bb",
    "a\u2028b",
    "a\u202eb",
    "a b",
    "x\udce9",
    "café.md",
    "My Note.md",
    "заметки.md",
    CRAFTED,
]


@pytest.mark.parametrize("name", INSIDE)
def test_a_name_inside_the_grammar_prints_as_itself_under_both_bounds(name: str) -> None:
    assert printable(name) == name
    assert quoted(name) == name


@pytest.mark.parametrize("name", OUTSIDE)
def test_a_name_outside_the_grammar_is_withheld_by_printable(name: str) -> None:
    # Mutation: return the name unchecked from `printable` — every case reddens.
    assert printable(name) == UNPRINTABLE
    assert printable(name, "<elsewhere>") == "<elsewhere>"


@pytest.mark.parametrize("name", OUTSIDE)
def test_a_name_outside_the_grammar_arrives_whole_and_inert_through_quoted(name: str) -> None:
    # The docstring's two claims, stated as properties: the name arrives whole (the literal reads
    # back to it) and cannot start a line or drive a terminal (every character is printable).
    # Mutation: return the name unchecked from `quoted`, or return `UNPRINTABLE` — each reddens.
    shown = quoted(name)
    assert ast.literal_eval(shown) == name
    assert shown.isprintable()
