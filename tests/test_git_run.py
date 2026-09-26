from __future__ import annotations

import locale
import os
import shutil
from pathlib import Path

import pytest

from keelline.gitenv import NO_ANSWER, git_run
from tests.gitfixture import plant_path

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


@needs_git
def test_a_path_the_locale_cannot_decode_is_answered_and_not_raised(tmp_path: Path) -> None:
    # `text=True` decoded strictly, so one non-UTF-8 name in `ls-files -z` either left every
    # caller as `internal error: UnicodeDecodeError` or, read as "no answer", hid every other
    # name in the same listing: a committed `.env` beside it went unreported, a sibling checkout
    # of the project passed `setup`'s common-directory check. The answer is the name itself,
    # spelled as the filesystem spells it — lossless, not a placeholder, which is what lets a
    # caller that matches it against a path it walked or sent still match. The name is planted
    # with `update-index --cacheinfo`, which takes the raw bytes on every platform, so this runs
    # where no such file can be created (APFS refuses one). Mutations (declared): the decode made
    # strict again -> it raises; the answer read as no answer again -> `(-1, "")`; both redden.
    git_run(tmp_path, "init", "-q")
    plant_path(tmp_path, LATIN1_NAME)
    code, out = git_run(tmp_path, "ls-files", "-z")
    assert (code, out) == (0, f"{DECODED_NAME}\0")
    assert os.fsencode(out.rstrip("\0")) == LATIN1_NAME


@needs_git
def test_a_name_sent_on_stdin_reaches_git_as_the_bytes_it_names(tmp_path: Path) -> None:
    # The other direction of the same seam: a name read off a Linux disk carries the surrogate
    # escapes above, and a strict encode of `stdin` failed before git was ever asked — the docs
    # trail's ignore filter then read "nothing is ignored" and listed a local-only document in
    # the committed roadmap. `check-ignore --no-index` echoes what it was sent, so an ignored
    # name coming back equal to itself proves both halves: the bytes git matched were the
    # name's own, and the answer decodes back to what the caller holds. Mutations (declared,
    # the two entries above) redden this too.
    git_run(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("caf*\n", encoding="utf-8")
    code, out = git_run(tmp_path, "check-ignore", "--no-index", "--stdin", "-z", stdin=DECODED_NAME)
    assert (code, out) == (0, f"{DECODED_NAME}\0")


@needs_git
def test_git_s_own_diagnostics_are_never_decoded_into_a_failure(tmp_path: Path) -> None:
    # `capture_output` decodes stderr with the same codec, and nothing reads it: a git whose
    # error text quoted one non-UTF-8 byte turned an ordinary non-zero exit — an answer every
    # caller has an arm for — into a traceback, or into `-1` with git's own exit code lost.
    # `update-index` on a missing path names it on stderr, raw. Mutations (declared, the two
    # entries above) redden this too.
    git_run(tmp_path, "init", "-q")
    code, out = git_run(tmp_path, "update-index", "--add", "--", DECODED_NAME)
    assert code not in (0, -1)
    assert out == ""


@needs_git
def test_a_stdin_this_process_cannot_encode_is_minus_one(tmp_path: Path) -> None:
    # A lone surrogate outside the escape range has no bytes under any codec, so git cannot be
    # asked the question at all: `(-1, "")`, the runner's own "git could not be given its
    # input", which every stdin caller already answers conservatively — `project.ignored`
    # refuses inside a work tree, `memory.refs` keeps the reference as unresolved. Reachable in
    # practice under a non-UTF-8 locale, where a note's text holds characters that locale has
    # no byte for. Mutation (declared): drop `UnicodeEncodeError` from the `except` -> this
    # reddens. `needs_git`, because where no `git` can be launched the `OSError` answers
    # `(-1, "")` first and the case passes whatever the `except` holds — measured, with that
    # mutation applied and no `git` on `PATH`: 1 passed.
    assert git_run(tmp_path, "check-ignore", "--stdin", stdin="\ud800") == (-1, "")


# A name that is valid UTF-8 and not ASCII: the filesystem spells it `café.md` on every
# platform where its encoding is UTF-8, which macOS's always is, whatever the locale says.
CAFE = "caf\u00e9.md"


def _a_latin_1_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """What `LC_ALL=en_US.ISO8859-1` changes in this process, simulated at the one place Python
    reads it, so the case holds on a runner that has no such locale installed."""
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: "latin-1")


@needs_git
def test_git_s_answer_and_the_filesystem_spell_a_name_alike_whatever_the_locale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `git_run` decoded with the locale's codec while `os.fsdecode`, `Path.iterdir` and argv use
    # the filesystem's, and on macOS the two differ under any non-UTF-8 locale: git's
    # `caf\xc3\xa9.md` came back as mojibake, never equal to the `café.md` the disk and argv
    # hold. Paths are compared with git's answers everywhere, so every such comparison missed.
    # The pipe uses the filesystem's codec now, and both directions agree. Mutation
    # (declared): decode with the locale's codec again -> this reddens.
    _a_latin_1_locale(monkeypatch)
    git_run(tmp_path, "init", "-q")
    plant_path(tmp_path, os.fsencode(CAFE))
    assert git_run(tmp_path, "ls-files", "-z") == (0, f"{CAFE}\0")


@needs_git
def test_a_name_asked_on_stdin_matches_the_rule_that_names_it_whatever_the_locale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The other direction: a name read off the disk, sent on `stdin` in the locale's codec,
    # reached git as bytes that were not the name's, so `.gitignore`'s `café.md` never matched
    # it and a gitignored document read as not ignored — the docs trail then listed it in the
    # committed roadmap. Mutation (declared, the entry above) reddens this too.
    _a_latin_1_locale(monkeypatch)
    git_run(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text(f"{CAFE}\n", encoding="utf-8")
    code, out = git_run(tmp_path, "check-ignore", "--no-index", "--stdin", "-z", stdin=CAFE)
    assert (code, out) == (0, f"{CAFE}\0")


def test_a_git_past_its_time_limit_is_minus_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The third cause `-1` still carries, and the one the callers' safeguards are kept for: a
    # `git` that hangs is no answer, whatever it would have said. The stand-in on `PATH` sleeps
    # past a bound far below it.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stand_in = bin_dir / "git"
    stand_in.write_text("#!/bin/sh\nexec sleep 5\n", encoding="utf-8")
    stand_in.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    assert git_run(tmp_path, "rev-parse", timeout=0.2) == (-1, "")


def test_no_answer_names_each_cause_git_run_folds_into_minus_one() -> None:
    # Callers word `-1` with this clause; a clause naming one cause misdiagnoses the others.
    # Output is no longer one of them — it is decoded losslessly — and a clause that still
    # named it would send an owner looking for a filename that is not the fault. Mutation
    # (advisory): put "not UTF-8" back into `NO_ANSWER` — this reddens.
    assert "could not be run" in NO_ANSWER
    assert "time limit" in NO_ANSWER
    assert "input" in NO_ANSWER
    assert "UTF-8" not in NO_ANSWER
