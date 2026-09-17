"""The one TOML serialiser, and the one rule it holds: a value is escaped or it is refused."""

from __future__ import annotations

import tomllib

import pytest

from keelline.errors import Refusal
from keelline.tomlout import dumps


def test_a_value_with_a_quote_and_a_newline_round_trips() -> None:
    # This module exists because the value it was written for is a git remote URL — repository-
    # authored bytes, by the Global Constraints' own list. Unescaped, a crafted URL closes its
    # own string and writes further keys into a record that decides what `attach` trusts.
    hostile = 'git@h:o/p.git"\nremote = "git@evil:o/p.git'
    parsed = tomllib.loads(dumps({"project": {"remote": hostile}}))
    assert parsed["project"] == {"remote": hostile}


def test_every_scalar_type_the_callers_use_round_trips() -> None:
    tables: dict[str, dict[str, object]] = {
        "project": {"remote": "u", "first_attach": "2026-09-17"},
        "machine": {"cli_on_path": True, "plugins": ["a", "b"]},
    }
    assert tomllib.loads(dumps(tables)) == tables


def test_an_unrepresentable_value_refuses_rather_than_being_mangled() -> None:
    # Silently dropping or str()-ing an unexpected type is how a capability record acquires a
    # value nobody wrote. There are two callers and both know their own types.
    with pytest.raises(Refusal):
        dumps({"project": {"when": object()}})


def test_a_key_that_is_not_a_bare_key_refuses_rather_than_being_quoted() -> None:
    # The same rule one level up. A key this cannot emit bare is a caller passing something it
    # did not mean to; quoting it would make `[project]` hold a name nobody chose to write.
    with pytest.raises(Refusal):
        dumps({"project": {"re mote": "u"}})
    with pytest.raises(Refusal):
        dumps({"pro ject": {"remote": "u"}})


def test_a_nested_table_refuses_rather_than_being_flattened() -> None:
    # This serialises flat tables and says so. A dict reaching a value position is a caller
    # expecting a shape this does not emit, and flattening it would write keys nobody asked for.
    with pytest.raises(Refusal):
        dumps({"project": {"remote": {"url": "u"}}})


def test_a_control_character_survives_the_round_trip() -> None:
    # A tab and a carriage return are legal in a TOML basic string only as escapes, and a raw
    # one is a parse error rather than a mangled value — which is the failure this would be if
    # the escaping table stopped at the quote and the backslash.
    value = "a\tb\rc\x00d\\e"
    assert tomllib.loads(dumps({"project": {"remote": value}}))["project"]["remote"] == value


def test_the_root_table_is_written_before_any_header() -> None:
    # `projects/<name>/project.toml` holds `remote` at the top level, because
    # `memory.store._bound` reads it there — one file, one place, or the writer and the reader
    # disagree about the record that decides whether a store resolves at all.
    text = dumps({"": {"remote": "u"}, "notes": {"kept": True}})
    assert text.splitlines()[0] == 'remote = "u"'
    assert tomllib.loads(text) == {"remote": "u", "notes": {"kept": True}}


def test_an_integer_round_trips() -> None:
    # The ledger format number and anything `setup` counts; `bool` is checked before `int`
    # because `isinstance(True, int)` is True and `1` is not `true`.
    assert tomllib.loads(dumps({"machine": {"format": 1}})) == {"machine": {"format": 1}}


def test_a_value_where_a_table_belongs_refuses() -> None:
    with pytest.raises(Refusal):
        dumps({"project": "not a table"})  # type: ignore[dict-item]
