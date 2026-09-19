"""DC5: the record of the three files the harness executes without Python, kept true on
every commit by `release check` and compared by `doctor files` on the installed copy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keelline.cli import build_parser, run
from keelline.release.commands import register
from keelline.release.hashes import HASHED_FILES, RECORD, digests, drift, read_record, write_record


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
