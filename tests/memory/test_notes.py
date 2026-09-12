from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from keelline.memory.notes import (
    UNRANKED,
    NoteError,
    NoteType,
    Provenance,
    read_note,
    render_note,
    walk,
    with_index,
    write_note,
)

FULL = """---
name: pick-a-fork
description: "At a fork, ask"
index: "A design fork → ask or decide"
group: Tests
group_order: 2
metadata:
  type: feedback
  startup: 2
  node_type: memory
  originSessionId: abc-123
---

Body line one.

Body line two.
"""

MINIMAL = """---
name: bare
description: just a description
---

Body.
"""

# Shapes the real corpus contains and a naive renderer destroys: an apostrophe that looks like
# a quote, an embedded double quote, a negative and a malformed `group_order`, and the native
# writer's own stamps.
AWKWARD = """---
name: awkward
description: 'tis a note, isn't it
index: "a → b"
group_order: -1
metadata:
  type: project
  modified: '2026-09-01T10:00:00Z'
  node_type: memory
---

Body with a "quoted" word.
"""

MALFORMED_ORDER = AWKWARD.replace("group_order: -1", "group_order: 2b")


def write(tmp_path: Path, text: str, name: str = "n.md") -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_every_declared_field_is_read(tmp_path: Path) -> None:
    note = read_note(write(tmp_path, FULL))
    assert note.name == "pick-a-fork"
    assert note.description == "At a fork, ask"
    assert note.index == "A design fork → ask or decide"
    assert note.group == "Tests"
    assert note.group_order == 2
    assert note.type is NoteType.FEEDBACK
    assert note.startup == 2
    assert note.body.startswith("Body line one.")


def test_an_absent_index_is_curated_by_default(tmp_path: Path) -> None:
    note = read_note(write(tmp_path, MINIMAL))
    assert note.index is None
    assert note.index_provenance is Provenance.CURATED


@pytest.mark.parametrize("text", [FULL, MINIMAL, AWKWARD, MALFORMED_ORDER])
def test_an_unmodified_note_round_trips_byte_for_byte(tmp_path: Path, text: str) -> None:
    # The strictest assertion in this module, and the reason the renderer keeps the original
    # lines rather than re-emitting parsed values: seventy notes whose quoting changed on the
    # first `memory index` is a diff nobody reviews and a ping-pong with the native writer.
    assert render_note(read_note(write(tmp_path, text))) == text


def test_an_apostrophe_is_not_read_as_a_quote(tmp_path: Path) -> None:
    assert read_note(write(tmp_path, AWKWARD)).description == "'tis a note, isn't it"


def test_a_malformed_group_order_is_kept_in_the_file(tmp_path: Path) -> None:
    # It parses to None — the renderer must still not delete the line it could not read.
    note = read_note(write(tmp_path, MALFORMED_ORDER))
    assert note.group_order is None
    assert "group_order: 2b" in render_note(note)


def test_an_absent_declared_key_is_never_invented_on_render(tmp_path: Path) -> None:
    # `read_note` defaults `description` to "" and `name` to the file stem so the fields are
    # always usable — but a read-time default is not a value this run decided to write. A
    # note without one of these keys must not gain a line it never had, in either direction.
    no_description = (
        "---\nname: reminder\ngroup: Tasks\nmetadata:\n  type: user\n---\n\nSome text.\n"
    )
    no_name = (
        "---\ndescription: a reminder\ngroup: Tasks\nmetadata:\n  type: user\n---\n\nSome text.\n"
    )
    assert render_note(read_note(write(tmp_path, no_description, "a.md"))) == no_description
    assert render_note(read_note(write(tmp_path, no_name, "b.md"))) == no_name


def test_the_native_writers_own_keys_survive_a_round_trip(tmp_path: Path) -> None:
    rendered = render_note(read_note(write(tmp_path, AWKWARD)))
    assert "modified: '2026-09-01T10:00:00Z'" in rendered
    assert "node_type: memory" in rendered


def test_only_a_changed_key_is_rewritten(tmp_path: Path) -> None:
    note = with_index(read_note(write(tmp_path, MINIMAL)), "trigger → answer", Provenance.NATIVE)
    rendered = render_note(note)
    assert "index_provenance: native" in rendered
    assert "description: just a description" in rendered  # untouched, unquoted, as it was
    # The new value is asserted by reading it back, not by its quoting: what the renderer owes
    # is a value that parses to what was set, and a style assertion would pin an accident.
    write(note.path.parent, rendered, note.path.name)
    assert read_note(note.path).index == "trigger → answer"


def test_write_note_persists_what_render_produced(tmp_path: Path) -> None:
    note = with_index(read_note(write(tmp_path, MINIMAL)), "t → a", Provenance.PROVISIONAL)
    write_note(note)
    again = read_note(note.path)
    assert again.index == "t → a"
    assert again.index_provenance is Provenance.PROVISIONAL


@pytest.mark.parametrize(
    "value,expected", [("2", 2), ("0", 0), ("false", None), ("no", None), ("off", None)]
)
def test_startup_reads_a_rank_or_a_refusal(
    tmp_path: Path, value: str, expected: int | None
) -> None:
    text = MINIMAL.replace("---\n\nBody.", f"metadata:\n  startup: {value}\n---\n\nBody.")
    assert read_note(write(tmp_path, text)).startup == expected


def test_an_unparsable_rank_sorts_last_rather_than_vanishing(tmp_path: Path) -> None:
    text = MINIMAL.replace("---\n\nBody.", "metadata:\n  startup: soon\n---\n\nBody.")
    assert read_note(write(tmp_path, text)).startup == UNRANKED


def test_as_of_is_a_date_or_none(tmp_path: Path) -> None:
    text = MINIMAL.replace("---\n\nBody.", "metadata:\n  as_of: 2026-09-01\n---\n\nBody.")
    assert read_note(write(tmp_path, text)).as_of == date(2026, 9, 1)
    assert read_note(write(tmp_path, MINIMAL, "b.md")).as_of is None


def test_a_malformed_as_of_is_none_not_an_error(tmp_path: Path) -> None:
    text = MINIMAL.replace("---\n\nBody.", "metadata:\n  as_of: soon\n---\n\nBody.")
    assert read_note(write(tmp_path, text)).as_of is None


def test_the_group_is_the_folder_never_the_frontmatter_key(tmp_path: Path) -> None:
    # `group` is a sub-heading inside a section; the section is the folder the note sits in.
    note = read_note(write(tmp_path, FULL, "developer/n.md"))
    assert note.group_name == "developer"
    assert note.group == "Tests"


def test_a_note_without_frontmatter_refuses(tmp_path: Path) -> None:
    with pytest.raises(NoteError, match="frontmatter"):
        read_note(write(tmp_path, "no frontmatter here\n"))


def test_an_unclosed_frontmatter_refuses(tmp_path: Path) -> None:
    with pytest.raises(NoteError, match="never closed"):
        read_note(write(tmp_path, "---\nname: a\n\nBody.\n"))


def test_a_nested_list_refuses_rather_than_being_dropped(tmp_path: Path) -> None:
    text = "---\nname: a\ndescription: b\ntags:\n  - one\n  - two\n---\n\nBody.\n"
    with pytest.raises(NoteError, match="line 4"):
        read_note(write(tmp_path, text))


def test_a_duplicated_key_refuses(tmp_path: Path) -> None:
    text = "---\nname: a\nname: b\ndescription: c\n---\n\nBody.\n"
    with pytest.raises(NoteError, match="duplicate"):
        read_note(write(tmp_path, text))


def test_a_doubly_signed_group_order_is_kept_but_never_raises(tmp_path: Path) -> None:
    # "--5".lstrip("-").isdigit() is True but int("--5") still raises: the guard that used to
    # gate this value let the ValueError through past read_note, and walk (which only catches
    # NoteError) crashed on it instead of quarantining the file — exactly the failure walk's
    # own docstring says a store cannot afford.
    text = AWKWARD.replace("group_order: -1", "group_order: --5")
    note = read_note(write(tmp_path, text, "developer/awkward.md"))
    assert note.group_order is None
    assert "group_order: --5" in render_note(note)
    found = walk(tmp_path, ["developer"])
    assert [n.name for n in found.notes] == ["awkward"]
    assert found.unreadable == []


def test_walk_reads_markdown_and_skips_the_rest(tmp_path: Path) -> None:
    (tmp_path / "developer").mkdir()
    write(tmp_path, MINIMAL, "developer/a.md")
    write(tmp_path, MINIMAL, "developer/.hidden.md")
    write(tmp_path, MINIMAL, "developer/_draft.md")
    (tmp_path / "developer" / "notes.txt").write_text("x", encoding="utf-8")
    found = walk(tmp_path, ["developer"])
    assert [note.path.name for note in found.notes] == ["a.md"]
    assert found.unreadable == []


def test_walk_quarantines_a_file_that_will_not_parse(tmp_path: Path) -> None:
    # The shipped preset ships `specs` in the default group list, and a store is a place
    # humans put things: one superseded document with no frontmatter must not cost the rest.
    (tmp_path / "specs").mkdir()
    write(tmp_path, MINIMAL, "specs/a.md")
    write(tmp_path, "a design document, no frontmatter\n", "specs/design.md")
    found = walk(tmp_path, ["specs"])
    assert [note.name for note in found.notes] == ["bare"]
    assert [path.name for path, _ in found.unreadable] == ["design.md"]


def test_walk_ignores_a_group_directory_that_does_not_exist(tmp_path: Path) -> None:
    assert walk(tmp_path, ["developer", "specs"]).notes == []
