"""`keelline upgrade` through the real parser: flags, exit codes, and what prints.

`init --no-ci` sets `[ci] mode = "none"`, so no case here asks the network for a pin.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from keelline.cli import build_parser, discover_registrars, run
from keelline.scaffold import Manifest
from tests.gitfixture import git, needs_git

FORGED = "docs/\x1b[31mforged.md"
# The commands every shared case runs through, and the invocations that print a report.
COMMANDS = ["upgrade"]
REPORTS = [("upgrade", "--dry-run")]
UNMATCHED = "note: 1 --force path(s) named no file this run had to judge"


def _run(root: Path, tmp_path: Path, *argv: str) -> tuple[int, dict[str, Any]]:
    """The command's `--json` object. A refusal goes to stderr in text mode (`cli._report`), so
    a test that read stdout alone would pass on an empty string."""
    parser = build_parser(discover_registrars())
    flags = ["--root", str(root), "--machine", str(tmp_path / "absent.toml"), "--json"]
    with redirect_stdout(io.StringIO()) as out:
        code = run([*argv, *flags], parser=parser)
    data: dict[str, Any] = json.loads(out.getvalue())
    return code, data


def _initialised(tmp_path: Path) -> Path:
    root = tmp_path / "widget"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", "git@github.com:owner/widget.git")
    code, data = _run(root, tmp_path, "init", "--yes", "--no-ci")
    assert code == 0, data["summary"]
    return root


def _forge_the_roadmap_target(root: Path) -> None:
    # A committed manifest can carry any `target`. The engine reports a left-behind file at the
    # recorded target, and a report prints targets; only one the path grammar accepts may print.
    manifest = Manifest.read(root)
    record = manifest.get("roadmap")
    assert record is not None
    manifest.with_record(replace(record, target=FORGED)).write(root)


@needs_git
@pytest.mark.parametrize("command", COMMANDS)
def test_an_uninitialised_repository_exits_two_and_names_what_to_run(
    tmp_path: Path, command: str
) -> None:
    root = tmp_path / "bare"
    root.mkdir()
    code, data = _run(root, tmp_path, command)
    assert code == 2 and "manifest.json is not there" in data["summary"]


@needs_git
def test_a_current_footprint_says_so_and_exits_zero(tmp_path: Path) -> None:
    root = _initialised(tmp_path)
    code, data = _run(root, tmp_path, "upgrade", "--dry-run")
    assert code == 0, data["summary"]
    assert data["summary"].splitlines()[0] == "would upgrade:"
    assert "0 to create, 0 to update, 0 to remove" in data["summary"]
    assert {
        "dry_run",
        "moved",
        "held",
        "footprint",
        "writes",
        "skipped",
        "orphans",
        "pin",
        "asked",
    } <= set(data)


@needs_git
@pytest.mark.parametrize("argv", REPORTS)
def test_a_recorded_target_outside_the_path_grammar_prints_as_its_artifact_id(
    tmp_path: Path, argv: tuple[str, ...]
) -> None:
    # `_relocation` answers a forged target with `skip_modified` at that target, and the run goes
    # on: exit 0, the file at the forged path untouched, and nothing of the target printed.
    root = _initialised(tmp_path)
    _forge_the_roadmap_target(root)
    code, data = _run(root, tmp_path, *argv)
    printed = json.dumps(data)
    assert code == 0, data["summary"]
    assert "\\u001b" not in printed and "forged" not in printed
    assert "<roadmap>" in data["summary"]


@needs_git
@pytest.mark.parametrize("command", COMMANDS)
def test_a_force_path_outside_the_root_is_refused_by_rule(tmp_path: Path, command: str) -> None:
    root = _initialised(tmp_path)
    code, data = _run(root, tmp_path, command, "--dry-run", "--force", "../elsewhere.md")
    assert code == 2
    assert "elsewhere" not in data["summary"]


@needs_git
def test_a_force_path_that_names_nothing_is_counted(tmp_path: Path) -> None:
    # The roadmap is edited first, so the exact path names an action the run judges and the
    # case-shifted one does not. On an untouched footprint every forced path would be counted,
    # whether or not the comparison worked. Mutation (advisory): count every forced path ->
    # the exact path gains a note and the first assertion reddens.
    root = _initialised(tmp_path)
    roadmap = root / "docs" / "roadmap.md"
    roadmap.write_text(roadmap.read_text(encoding="utf-8") + "\nours\n", encoding="utf-8")
    code, data = _run(root, tmp_path, "upgrade", "--dry-run", "--force", "docs/roadmap.md")
    assert code == 0 and UNMATCHED not in data["summary"]
    code, data = _run(root, tmp_path, "upgrade", "--dry-run", "--force", "docs/Roadmap.md")
    assert code == 0
    assert UNMATCHED in data["summary"]
