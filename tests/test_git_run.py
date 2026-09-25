from __future__ import annotations

import os
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


# A byte no UTF-8 locale decodes, and the string this process spells it as: `os.fsdecode` is
# how `os.listdir`, `Path.iterdir` and `sys.argv` hand the same name to Python, so it is the
# one spelling a git answer can be compared with, and the one that opens the file it names.
LATIN1_NAME = b"caf\xe9.md"
DECODED_NAME = os.fsdecode(LATIN1_NAME)


def _stage_without_a_file(root: Path, name: str) -> None:
    """Put `name` in the index with no file on disk.

    Measured rather than assumed: APFS refuses to create a non-UTF-8 filename, so a real file
    would make this case Linux-only, while `update-index --cacheinfo` takes the raw bytes and
    `ls-files` prints them back raw on every platform. The argument reaches git as those bytes
    because `subprocess` encodes argv with `os.fsencode`.
    """
    code, blob = git_run(root, "hash-object", "-w", "--stdin", stdin="x")
    assert code == 0
    code, _ = git_run(root, "update-index", "--add", "--cacheinfo", f"100644,{blob.strip()},{name}")
    assert code == 0


@needs_git
def test_a_path_the_locale_cannot_decode_is_answered_and_not_raised(tmp_path: Path) -> None:
    # `text=True` decoded strictly and `git_run` caught only `OSError`/`SubprocessError`, so a
    # non-UTF-8 name in `ls-files -z` left every caller as `internal error:
    # UnicodeDecodeError`. The answer is now the name itself, spelled as the filesystem spells
    # it — a lossless answer, not a placeholder, which is what lets a caller that matches it
    # against a path it walked or sent still match. Mutation (declared): drop
    # `errors="surrogateescape"` -> the decode raises again and this reddens.
    git_run(tmp_path, "init", "-q")
    _stage_without_a_file(tmp_path, DECODED_NAME)
    code, out = git_run(tmp_path, "ls-files", "-z")
    assert (code, out) == (0, f"{DECODED_NAME}\0")
    assert os.fsencode(out.rstrip("\0")) == LATIN1_NAME


@needs_git
def test_a_name_sent_on_stdin_reaches_git_as_the_bytes_it_names(tmp_path: Path) -> None:
    # The other direction of the same seam: a name read off the disk carries the surrogate
    # escapes above, and a strict encode of `stdin` raised `UnicodeEncodeError` before git
    # was ever asked. `check-ignore --no-index` echoes what it was sent, so an ignored name
    # coming back equal to itself proves both halves: the bytes git matched were the name's
    # own, and the answer decodes back to what the caller holds. `project.ignored` refuses on
    # exactly this intersection. Mutation (declared, the entry above): drop
    # `errors="surrogateescape"` -> the encode raises and this reddens.
    git_run(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("caf*\n", encoding="utf-8")
    code, out = git_run(tmp_path, "check-ignore", "--no-index", "--stdin", "-z", stdin=DECODED_NAME)
    assert (code, out) == (0, f"{DECODED_NAME}\0")


@needs_git
def test_git_s_own_diagnostics_are_never_decoded_into_a_failure(tmp_path: Path) -> None:
    # `capture_output` decodes stderr with the same codec, and nothing reads it: a git whose
    # error text quoted one non-UTF-8 byte turned an ordinary non-zero exit — an answer every
    # caller has an arm for — into a traceback. `update-index` on a missing path names it on
    # stderr, raw. Mutation (declared, the entry above) reddens this too.
    git_run(tmp_path, "init", "-q")
    code, out = git_run(tmp_path, "update-index", "--add", "--", DECODED_NAME)
    assert code != 0
    assert out == ""


def test_a_stdin_this_process_cannot_encode_is_minus_one(tmp_path: Path) -> None:
    # A lone surrogate outside the escape range has no bytes under any codec, so git cannot be
    # asked the question at all: `(-1, "")`, the runner's own "git could not be run", which
    # every stdin caller already answers conservatively — `project.ignored` refuses inside a
    # work tree, `memory.refs` keeps the reference as unresolved. Reachable in practice under a
    # non-UTF-8 locale, where a note's text holds characters that locale has no byte for.
    # Mutation (declared): drop `UnicodeEncodeError` from the `except` -> this reddens.
    assert git_run(tmp_path, "check-ignore", "--stdin", stdin="\ud800") == (-1, "")
