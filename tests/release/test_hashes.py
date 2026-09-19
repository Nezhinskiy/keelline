"""DC5: the record of the three files the harness executes without Python, kept true on
every commit by `release check` and compared by `doctor files` on the installed copy."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from keelline.cli import build_parser, run
from keelline.errors import Failure
from keelline.release.commands import register
from keelline.release.hashes import (
    HASHED_FILES,
    RECORD,
    UnreadableRecord,
    digests,
    drift,
    read_record,
    write_record,
)


def _plugin(tmp_path: Path) -> Path:
    for relative in HASHED_FILES:
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(f"# {relative}\n", encoding="utf-8")
    return tmp_path


def test_a_written_record_has_no_drift_and_one_changed_byte_is_named(tmp_path: Path) -> None:
    # Mutation (declared): `drift` compares the record against itself -> the second
    # assertion reddens (no drift after the edit).
    root = _plugin(tmp_path)
    write_record(root)
    assert drift(root) == []
    (root / "hooks" / "run-hook.sh").write_text("# changed\n", encoding="utf-8")
    assert drift(root) == [
        f"{RECORD} does not match hooks/run-hook.sh; run `keelline release hashes`"
    ]


def test_the_record_is_json_with_a_format_and_one_digest_per_file(tmp_path: Path) -> None:
    root = _plugin(tmp_path)
    write_record(root)
    document = json.loads((root / RECORD).read_text(encoding="utf-8"))
    assert document["format"] == 1
    assert set(document["files"]) == set(HASHED_FILES)
    assert document["files"] == digests(root)
    assert read_record(root) == digests(root)


def test_no_record_reads_as_none_and_a_missing_file_is_drift(tmp_path: Path) -> None:
    root = _plugin(tmp_path)
    assert read_record(root) is None
    assert drift(root) == [f"{RECORD} is missing; run `keelline release hashes`"]
    write_record(root)
    (root / "scripts" / "keelline").unlink()
    assert drift(root) == [f"{RECORD} names scripts/keelline, which is not in the tree"]


def test_the_cli_writes_the_record_and_check_exits_one_on_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The command's argv wiring, which nothing else holds: that `hashes` is registered is held
    # by the README row walk, which parses every row against the real parser, but that `--check`
    # reaches `drift` and that the bare form writes is only here. No subprocess anywhere — this
    # command reads and hashes files and nothing else.
    root = _plugin(tmp_path)
    parser = build_parser([register])
    assert run(["release", "hashes", "--check", "--root", str(root)], parser=parser) == 1
    assert "is missing" in capsys.readouterr().err
    assert run(["release", "hashes", "--root", str(root)], parser=parser) == 0
    assert (root / RECORD).is_file()
    assert run(["release", "hashes", "--check", "--root", str(root)], parser=parser) == 0
    (root / "hooks" / "hooks.json").write_text("# moved\n", encoding="utf-8")
    assert run(["release", "hashes", "--check", "--root", str(root)], parser=parser) == 1
    assert "hooks/hooks.json" in capsys.readouterr().err


def test_a_record_that_is_not_json_is_unreadable_rather_than_absent(tmp_path: Path) -> None:
    # The two answers are different on purpose and the callers branch on the difference: an
    # absent record skips in `doctor` and an unreadable one must be red. A decoder error that
    # read as `None` would turn a corrupted record into a quiet skip — the loudest possible
    # way to say nothing. Mutation (declared): return `None` instead -> both raises redden.
    root = _plugin(tmp_path)
    (root / RECORD).write_text("{not json\n", encoding="utf-8")
    with pytest.raises(UnreadableRecord, match="not valid JSON"):
        read_record(root)
    with pytest.raises(UnreadableRecord):
        drift(root)


@pytest.mark.parametrize(
    "body",
    [
        '{"format": 2, "files": {}}',
        '{"format": 1, "files": []}',
        '{"format": 1, "files": {"hooks/hooks.json": 1}}',
        '{"files": {}}',
        "[]",
    ],
    ids=[
        "another-format",
        "files-not-a-table",
        "a-digest-that-is-not-a-string",
        "no-format",
        "not-an-object",
    ],
)
def test_a_record_of_the_wrong_shape_is_unreadable(tmp_path: Path, body: str) -> None:
    # Valid JSON of the wrong shape decodes cleanly, so the decoder catch above never sees it —
    # the same class of hole `versions._parse` had for a lockfile that was valid TOML of the
    # wrong shape. Mutation (declared): stop checking `format` -> the first case reads as a
    # record with no files and this reddens.
    root = _plugin(tmp_path)
    (root / RECORD).write_text(body + "\n", encoding="utf-8")
    with pytest.raises(UnreadableRecord):
        read_record(root)


def test_a_tree_missing_a_shipped_file_cannot_be_recorded_at_all(tmp_path: Path) -> None:
    # A record that names two of three files is a record saying "this is what the release
    # shipped" while naming less than it did, and every reader of it afterwards reports drift
    # against a claim nobody meant to make. Refused at the moment of writing, where the tree
    # can still be fixed — and nothing is written. Mutation (declared): drop the length check
    # -> a partial record lands and both assertions redden.
    root = _plugin(tmp_path)
    (root / "hooks" / "hooks.json").unlink()
    with pytest.raises(Failure, match=re.escape("hooks/hooks.json")):
        write_record(root)
    assert not (root / RECORD).exists(), "a refusal wrote a partial record anyway"
