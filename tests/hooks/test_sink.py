from __future__ import annotations

import json
import re
from pathlib import Path

from keelline.hooks.api import NullSink
from keelline.hooks.sink import (
    DIAGNOSTIC_FIELD_CHARS,
    DIAGNOSTICS,
    DIAGNOSTICS_MAX_BYTES,
    MARKERS,
    ROTATED,
    sink_for,
)

HEX32 = re.compile(r"\A[0-9a-f]{32}\Z")


def test_no_plugin_data_means_a_sink_that_forgets() -> None:
    # The ordinary state outside a harness: `keelline hook` run by hand, or by a test. It must
    # degrade, not raise — a sink failure would take the whole dispatch with it.
    assert isinstance(sink_for("s1", {}), NullSink)


def test_a_marker_is_remembered_across_processes(tmp_path: Path) -> None:
    # The whole point: `NullSink.seen()` is always False, so `once_key` means "every
    # invocation" until this exists, and a once-per-context notice fires on every tool call.
    first = sink_for("s1", {"CLAUDE_PLUGIN_DATA": str(tmp_path)})
    assert first.seen("ledger-notes") is False
    first.mark("ledger-notes")
    second = sink_for("s1", {"CLAUDE_PLUGIN_DATA": str(tmp_path)})
    assert second.seen("ledger-notes") is True


def test_a_different_session_does_not_inherit_markers(tmp_path: Path) -> None:
    sink_for("s1", {"CLAUDE_PLUGIN_DATA": str(tmp_path)}).mark("ledger-notes")
    assert sink_for("s2", {"CLAUDE_PLUGIN_DATA": str(tmp_path)}).seen("ledger-notes") is False


def test_a_marker_lands_at_two_hashed_segments_and_nowhere_else(tmp_path: Path) -> None:
    # The POSITIVE shape, asserted rather than "nothing escaped". An earlier draft asserted
    # only that every written path stayed under tmp_path, which holds with the hash deleted:
    # `../../escape` from `<data>/keelline/markers/<session>/` lands back inside `<data>`, just
    # not under `markers/`. All three of its assertions passed with the guard broken.
    data = {"CLAUDE_PLUGIN_DATA": str(tmp_path)}
    sink_for("../../session", data).mark("../../escape")
    markers = tmp_path / "keelline" / MARKERS
    written = [p for p in markers.rglob("*") if p.is_file()]
    assert len(written) == 1
    marker = written[0]
    assert marker.parent.parent == markers
    assert HEX32.match(marker.parent.name) and HEX32.match(marker.name)


def test_a_hostile_segment_never_reaches_the_filesystem_walk(tmp_path: Path) -> None:
    # The backstop under the hash, asserted separately so that removing either control is
    # visible. `fsops._checked` refuses `..`, an absolute path and an empty component by
    # construction, so a future edit that stops hashing cannot silently start traversing.
    data = {"CLAUDE_PLUGIN_DATA": str(tmp_path)}
    sink_for("s1", data).mark("../../escape")
    assert not (tmp_path.parent / "escape").exists()
    assert not (tmp_path / "keelline" / "escape").exists()


def test_a_diagnostic_never_carries_a_payload_verbatim(tmp_path: Path) -> None:
    # §5.3: "never raw stdin". A handler's exception message can quote a repository's bytes, so
    # every FIELD is capped before serialisation — capping the serialised line instead cuts
    # inside whichever field sorts first, and `json.loads` then raises on the record `doctor`
    # is supposed to read.
    sink = sink_for("s1", {"CLAUDE_PLUGIN_DATA": str(tmp_path)})
    sink.diagnostic({"event": "PreToolUse", "handler": "bg-cleanup", "error": "X" * 50_000})
    line = (tmp_path / "keelline" / DIAGNOSTICS).read_text(encoding="utf-8").splitlines()[0]
    record = json.loads(line)
    assert record["handler"] == "bg-cleanup"
    assert len(record["error"]) < 50_000


def test_the_session_a_record_is_filed_under_is_capped_like_any_other_field(
    tmp_path: Path,
) -> None:
    # The session id is off the hook's stdin, type-checked by `parse_event` as `str` and no
    # more, so it is payload-controlled exactly as a handler's reason string is. Merged into the
    # record after the cap — which is where it started — it was the one field a repository could
    # write to this log at any length it liked.
    sink = sink_for("S" * 50_000, {"CLAUDE_PLUGIN_DATA": str(tmp_path)})
    sink.diagnostic({"event": "PreToolUse", "handler": "bg-cleanup", "error": "boom"})
    line = (tmp_path / "keelline" / DIAGNOSTICS).read_text(encoding="utf-8").splitlines()[0]
    assert len(json.loads(line)["session"]) == DIAGNOSTIC_FIELD_CHARS


def test_the_log_is_rotated_rather_than_grown(tmp_path: Path) -> None:
    sink = sink_for("s1", {"CLAUDE_PLUGIN_DATA": str(tmp_path)})
    for _ in range(4_000):
        sink.diagnostic({"event": "PreToolUse", "handler": "bg-cleanup", "error": "Y" * 200})
    live = tmp_path / "keelline" / DIAGNOSTICS
    assert live.stat().st_size <= DIAGNOSTICS_MAX_BYTES
    assert (tmp_path / "keelline" / ROTATED).exists()


def test_old_sessions_are_pruned_and_the_newest_survives(tmp_path: Path) -> None:
    # Sessions are unbounded in number and a marker is worthless once its session ends, so
    # without a prune the directory grows for the life of the machine. The assertion is that
    # the prune keeps the RIGHT ones: a prune that dropped the newest would still bound growth.
    data = {"CLAUDE_PLUGIN_DATA": str(tmp_path)}
    for index in range(60):
        sink_for(f"s{index}", data).mark("k")
    kept = list((tmp_path / "keelline" / MARKERS).iterdir())
    assert len(kept) <= 50
    assert sink_for("s59", data).seen("k") is True


def test_an_unwritable_data_directory_degrades_instead_of_raising(tmp_path: Path) -> None:
    # A hook runs on every tool call; a read-only ${CLAUDE_PLUGIN_DATA} must cost a lost
    # marker, never a refused Bash command.
    blocked = tmp_path / "ro"
    blocked.mkdir(mode=0o500)
    assert isinstance(sink_for("s1", {"CLAUDE_PLUGIN_DATA": str(blocked)}), NullSink)
