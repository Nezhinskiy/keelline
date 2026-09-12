from __future__ import annotations

import json

import pytest

from keelline.scaffold.entries import (
    EntriesError,
    apply_entries,
    mark,
    marker_id,
    owned,
    owned_ids,
)


def document(*commands: tuple[str, str]) -> str:
    return json.dumps(
        {
            "hooks": {
                event: [{"matcher": "Bash", "hooks": [{"type": "command", "command": cmd}]}]
                for event, cmd in commands
            }
        },
        indent=2,
    )


def commands_of(text: str, event: str) -> list[str]:
    # `.get("hooks", {})` and not `["hooks"]`: apply_entries drops an empty "hooks" key
    # entirely, which is exactly what the retired-id case leaves behind.
    raw = json.loads(text)
    return [
        hook["command"] for group in raw.get("hooks", {}).get(event, []) for hook in group["hooks"]
    ]


def wanted(event: str, entry_id: str, command: str) -> dict[str, list[dict[str, object]]]:
    return {
        event: [
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": mark(command, entry_id)}],
            }
        ]
    }


def test_marker_id_reads_the_id_a_command_claims() -> None:
    assert marker_id("run.sh hook PreToolUse  # keelline:bg-cleanup") == "bg-cleanup"
    assert marker_id("run.sh hook PreToolUse") is None


def test_a_marker_that_is_not_at_the_end_is_not_an_id() -> None:
    assert marker_id("run.sh  # keelline:bg-cleanup then more text") is None


def test_mark_is_idempotent() -> None:
    once = mark("run.sh", "bg-cleanup")
    assert mark(once, "bg-cleanup") == once


def test_a_marked_entry_is_replaced() -> None:
    before = document(("PreToolUse", mark("old.sh", "bg-cleanup")))
    after = apply_entries(before, wanted("PreToolUse", "bg-cleanup", "new.sh"))
    assert commands_of(after, "PreToolUse") == [mark("new.sh", "bg-cleanup")]


def test_a_foreign_entry_is_left_alone() -> None:
    before = document(("PreToolUse", "someone-elses-guard.sh"))
    after = apply_entries(before, wanted("PreToolUse", "bg-cleanup", "new.sh"))
    assert "someone-elses-guard.sh" in commands_of(after, "PreToolUse")


def test_a_group_mixing_a_marked_and_a_foreign_entry_keeps_the_foreign_one() -> None:
    raw = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "theirs.sh"},
                        {"type": "command", "command": mark("old.sh", "bg-cleanup")},
                    ],
                }
            ]
        }
    }
    after = apply_entries(json.dumps(raw), wanted("PreToolUse", "bg-cleanup", "new.sh"))
    assert commands_of(after, "PreToolUse") == ["theirs.sh", mark("new.sh", "bg-cleanup")]


def test_a_retired_id_is_removed() -> None:
    before = document(("PreToolUse", mark("old.sh", "retired")))
    after = apply_entries(before, {})
    assert commands_of(after, "PreToolUse") == []
    assert "hooks" not in json.loads(after)


def test_an_event_with_no_keelline_entry_is_untouched() -> None:
    before = document(("PostToolUse", "theirs.sh"))
    after = apply_entries(before, wanted("PreToolUse", "bg-cleanup", "new.sh"))
    assert commands_of(after, "PostToolUse") == ["theirs.sh"]


def test_unrelated_top_level_keys_survive() -> None:
    raw = json.loads(document(("PreToolUse", "theirs.sh")))
    raw["permissions"] = {"deny": ["Read(./.env)"]}
    after = apply_entries(json.dumps(raw), wanted("PreToolUse", "bg", "new.sh"))
    assert json.loads(after)["permissions"] == {"deny": ["Read(./.env)"]}


def test_owned_covers_only_the_marked_entries() -> None:
    # The stamp the manifest records. A user's unrelated edit beside the hooks must not read
    # as a hand edit of Keelline's own entries, or `upgrade` freezes them forever.
    with_ours = apply_entries(
        document(("PreToolUse", "theirs.sh")), wanted("PreToolUse", "bg", "x")
    )
    raw = json.loads(with_ours)
    raw["permissions"] = {"deny": ["Read(./.env)"]}
    assert owned(with_ours) == owned(json.dumps(raw))
    assert "theirs.sh" not in owned(with_ours)
    assert "keelline:bg" in owned(with_ours)


def test_owned_is_insensitive_to_the_key_order_inside_an_entry() -> None:
    # The load-bearing half of the stamp. Reordering the keys of an entry changes no value, so
    # the stamp must not move: if it does, the artifact reads as hand-edited for good, and the
    # next `--force` writes the same bytes back and still disagrees with the record.
    installed = apply_entries("", wanted("PreToolUse", "bg-cleanup", "new.sh"))
    raw = json.loads(installed)
    entry = raw["hooks"]["PreToolUse"][0]["hooks"][0]
    reordered = dict(reversed(list(entry.items())))
    assert list(reordered) != list(entry)
    raw["hooks"]["PreToolUse"][0]["hooks"][0] = reordered
    assert owned(json.dumps(raw)) == owned(installed)


def test_owned_ids_reports_event_by_id() -> None:
    before = document(("PreToolUse", mark("a.sh", "bg-cleanup")))
    assert owned_ids(before) == {"bg-cleanup": "PreToolUse"}


def test_a_malformed_document_refuses() -> None:
    with pytest.raises(EntriesError):
        apply_entries("{not json", {})


def test_an_empty_document_gains_the_wanted_entries() -> None:
    after = apply_entries("", wanted("PreToolUse", "bg-cleanup", "new.sh"))
    assert commands_of(after, "PreToolUse") == [mark("new.sh", "bg-cleanup")]
