from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from keelline.gitenv import git_run

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


@needs_git
def test_a_successful_query_returns_zero_and_its_output(tmp_path: Path) -> None:
    code, out = git_run(tmp_path, "init", "-q")
    assert (code, out) == (0, "")
    code, out = git_run(tmp_path, "rev-parse", "--is-inside-work-tree")
    assert (code, out.strip()) == (0, "true")


@needs_git
def test_a_non_zero_exit_is_returned_not_collapsed(tmp_path: Path) -> None:
    # `check-ignore` answers 1 for "nothing matched"; a runner that read every non-zero as
    # "nothing found" could not carry that answer. Mutation: return `(-1, "")` on any
    # non-zero — this reddens.
    git_run(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("x\n", encoding="utf-8")
    code, _ = git_run(tmp_path, "check-ignore", "--no-index", "--stdin", stdin="y\n")
    assert code == 1


def test_a_git_that_cannot_run_is_minus_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))  # no git here
    assert git_run(tmp_path, "rev-parse") == (-1, "")


@needs_git
def test_the_environment_is_scrubbed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # An inherited GIT_DIR would make every answer be about a different repository.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    git_run(elsewhere, "init", "-q")
    monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))
    code, _ = git_run(tmp_path, "rev-parse", "--is-inside-work-tree")
    assert code != 0
