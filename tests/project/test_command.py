"""`keelline init` through the real parser: the flags, the exit codes and the `--json` keys.

Every case passes `--no-ci`, and that is what keeps this module offline: with `[ci] mode` set
to `none` the run never asks the release area to resolve a pin, so `subprocess_runner()` — the
runner `commands.py` builds, and the one thing here that is not a stub — is never handed a
`git ls-remote` against the public repository. `tests/project/test_init.py` drives the pinned
half in-process with a stub runner instead.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run
from tests.gitfixture import git, needs_git

JSON_KEYS = {"dry_run", "adopted", "once", "footprint", "writes", "skipped", "pin", "asked", "note"}


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "widget"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", "git@github.com:owner/widget.git")
    return root


def _invoke(root: Path, tmp_path: Path, *argv: str) -> tuple[int, str]:
    parser = build_parser(discover_registrars())
    flags = ["--root", str(root), "--machine", str(tmp_path / "absent.toml")]
    with redirect_stdout(io.StringIO()) as out:
        code = run(["init", *argv, "--no-ci", *flags], parser=parser)
    return code, out.getvalue()


@needs_git
def test_without_yes_the_command_refuses_and_names_the_lane_that_ships_the_questions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    code, printed = _invoke(root, tmp_path)
    assert code == 2 and printed == ""
    stderr = capsys.readouterr().err
    assert "onboarding lane" in stderr and "--yes" in stderr
    assert not (root / ".keelline").exists()


@needs_git
def test_a_dry_run_prints_both_reports_and_says_it_wrote_nothing(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    code, printed = _invoke(root, tmp_path, "--yes", "--dry-run", "--json")
    assert code == 0, printed
    data = json.loads(printed)
    assert set(data) >= JSON_KEYS and data["dry_run"] is True
    # Two reports, not one rendered twice: the write-once pass plans three files and the
    # footprint pass plans the rest, and a summary that showed one of them would hide
    # whichever half a refusal landed in.
    assert "CLAUDE.md" in data["once"] and "CLAUDE.md" not in data["footprint"]
    assert ".gitignore" in data["footprint"]
    assert data["adopted"] is False and data["pin"] is None
    assert set(data["writes"]) >= {"CLAUDE.md", "keelline.toml", ".gitignore"}
    assert not (root / "CLAUDE.md").exists()


@needs_git
def test_a_real_run_summarises_both_passes_and_the_ci_line(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    code, printed = _invoke(root, tmp_path, "--yes")
    assert code == 0, printed
    assert printed.startswith("initialised:")
    assert "write-once:" in printed and "footprint:" in printed
    assert "CI: skipped — [ci] mode is none" in printed
    assert (root / ".keelline" / "manifest.json").is_file()


@needs_git
def test_a_refused_footprint_exits_one_with_the_refused_section_in_that_report(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    (root / "AGENTS.md").write_text("# Mine\n\n<!-- keelline:harness:end -->\n", encoding="utf-8")
    code, printed = _invoke(root, tmp_path, "--yes", "--json")
    assert code == 1, printed
    data = json.loads(printed)
    assert "REFUSED" in data["footprint"] and "REFUSED" not in data["once"]
    assert not (root / ".keelline").exists()
