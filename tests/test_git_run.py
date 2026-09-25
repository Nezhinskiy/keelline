from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from keelline.gitenv import NO_ANSWER, git_run

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


@needs_git
def test_the_product_s_git_reads_the_home_the_suite_gives_each_test(tmp_path: Path) -> None:
    # `scrubbed_env` keeps `HOME` for real users, so under test the product's `git` would read
    # the developer's global excludes; `tests/conftest.py` gives each test an empty one. This
    # writes an excludes file there and sees the product's `check-ignore` honour it, so the
    # `HOME` it reads is the sealed one and not the developer's. Mutation (advisory): drop the
    # conftest's `setenv("HOME", ...)` -> the first assertion reddens, before anything could be
    # written into the developer's real home.
    home = Path.home()
    assert home.is_relative_to(tmp_path.parent), home
    (home / ".config" / "git").mkdir(parents=True)
    (home / ".config" / "git" / "ignore").write_text("CLAUDE.md\n", encoding="utf-8")
    git_run(tmp_path, "init", "-q")
    code, out = git_run(tmp_path, "check-ignore", "--stdin", "-z", stdin="CLAUDE.md\0other.md")
    assert (code, out) == (0, "CLAUDE.md\0")


@needs_git
def test_a_committed_path_that_is_not_utf_8_is_no_answer_and_not_a_traceback(
    tmp_path: Path,
) -> None:
    # `text=True` decodes strictly, and `-z` makes git print a tracked name raw: one index entry
    # whose name is not UTF-8 raised `UnicodeDecodeError` out of `git_run`, and so out of the
    # `plan` gate (`diff --name-only -z`) and `keelline plan check`. The name is planted with
    # `update-index --cacheinfo`, which takes the raw bytes on every platform, so this runs
    # where no such file can be created (APFS refuses one). Mutation (declared): drop
    # `UnicodeError` from the `except` — the decode error escapes and this reddens.
    git_run(tmp_path, "init", "-q")
    code, blob = git_run(tmp_path, "hash-object", "-w", "--stdin", stdin="planted\n")
    assert code == 0
    name = os.fsdecode(b".env\xe9")
    code, _ = git_run(
        tmp_path, "update-index", "--add", "--cacheinfo", f"100644,{blob.strip()},{name}"
    )
    assert code == 0
    assert git_run(tmp_path, "ls-files", "-z") == (-1, "")


@needs_git
def test_a_question_that_is_not_utf_8_is_no_answer_and_not_a_traceback(tmp_path: Path) -> None:
    # The same boundary the other way: `stdin` is encoded strictly, and a path read off a Linux
    # disk carries a surrogate for each byte that is not UTF-8, and the roadmap's listing asks
    # `check-ignore --stdin` about every document it finds on disk. Mutation (declared, the entry
    # above): drop `UnicodeError` from the `except` — `UnicodeEncodeError` escapes.
    git_run(tmp_path, "init", "-q")
    asked = os.fsdecode(b"caf\xe9.md")
    assert git_run(tmp_path, "check-ignore", "--no-index", "--stdin", "-z", stdin=asked) == (-1, "")


def test_no_answer_names_each_cause_git_run_folds_into_minus_one() -> None:
    # Callers word `-1` with this clause; a clause naming one cause misdiagnoses the other two.
    # Mutation (advisory): drop "not UTF-8 text" from `NO_ANSWER` — this reddens.
    assert "could not be run" in NO_ANSWER
    assert "time limit" in NO_ANSWER
    assert "not UTF-8 text" in NO_ANSWER
