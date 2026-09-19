"""DC9: one failing command, run three times, and a verdict the three exit codes determine.

The working tree is read once and never written: HEAD and the merge-base are extracted with
`git archive` into a scratch directory. The command itself is the caller's — `uv sync
--locked && uv run pytest …` is what makes run 2 and run 3 "synced" — so the tool is the
same for every stack.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from keelline.errors import Failure
from keelline.guards.attribute import VERDICTS, attribute
from keelline.runner import NOT_FOUND, TIMED_OUT, Completed

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


@dataclass
class _Coded:
    """A runner that answers by the directory it is run in: the tree decides the exit code."""

    codes: dict[str, int]
    calls: list[tuple[list[str], Path]] = field(default_factory=list)
    trees: dict[str, dict[str, str]] = field(default_factory=dict)

    def run(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append((argv, cwd))
        self.trees[cwd.name] = {
            str(p.relative_to(cwd)): p.read_text(encoding="utf-8")
            for p in cwd.rglob("*")
            if p.is_file() and ".git" not in p.parts
        }
        return Completed(self.codes.get(cwd.name, 0), "", "")


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull},
    )
    return done.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    """`main` with one commit, then `feature` with one more, then `main` advanced past the fork."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "base")
    _git(root, "switch", "-qc", "feature")
    (root / "a.txt").write_text("feature\n", encoding="utf-8")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qam", "feature")
    _git(root, "switch", "-q", "main")
    (root / "later.txt").write_text("later\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "later")
    _git(root, "switch", "-q", "feature")
    return root


@needs_git
def test_the_three_runs_land_in_the_working_tree_head_and_the_merge_base(tmp_path: Path) -> None:
    # Run 1 is the working tree as it is; run 2 is HEAD's committed tree; run 3 is the
    # merge-base with `--base`, NOT the base's tip — a base that advanced after the fork would
    # otherwise leak later commits into the "before" side. Proved from the files the archives
    # left: the head copy carries the feature edit, the base copy carries neither the feature
    # edit nor `later.txt`.
    #
    # Mutation (declared): archive `base` instead of `merge_base` -> the base copy carries
    # `later.txt` and the last assertion reddens.
    root = _repo(tmp_path)
    (root / "a.txt").write_text("uncommitted\n", encoding="utf-8")
    runner = _Coded({})
    result = attribute(root, command="true", base="main", runner=runner)
    assert [cwd.name for _, cwd in runner.calls] == ["repo", "head", "base"]
    assert all(argv == ["sh", "-c", "true"] for argv, _ in runner.calls)
    # The scratch directory is gone when `attribute` returns, so the stub snapshots each
    # tree at call time (`_Coded.trees`) and the assertions are over the snapshots.
    head, base = runner.trees["head"], runner.trees["base"]
    assert head["a.txt"] == "feature\n"
    assert base["a.txt"] == "base\n"
    assert "later.txt" not in base
    assert (root / "a.txt").read_text(encoding="utf-8") == "uncommitted\n"
    assert result.merge_base == _git(root, "merge-base", "HEAD", "main")


@needs_git
@pytest.mark.parametrize(
    ("codes", "verdict"),
    [
        ({"head": 1, "base": 1}, VERDICTS[0]),  # pre-existing: not this change
        ({"head": 1, "base": 0}, VERDICTS[1]),  # this change
        ({"head": 0, "base": 1}, VERDICTS[2]),  # this change fixed a pre-existing failure
        ({"repo": 1, "head": 0, "base": 0}, VERDICTS[3]),  # environmental
        ({}, VERDICTS[4]),  # not reproduced
    ],
)
def test_each_verdict_follows_from_its_exit_codes(
    tmp_path: Path, codes: dict[str, int], verdict: str
) -> None:
    # The verdict table, one row per assertion. Mutation (declared): swap the "this change"
    # and "pre-existing" arms -> two rows redden.
    root = _repo(tmp_path)
    result = attribute(root, command="true", base="main", runner=_Coded(codes))
    assert result.verdict == verdict


@needs_git
@pytest.mark.parametrize("code", [TIMED_OUT, NOT_FOUND])
def test_a_run_that_did_not_execute_is_a_failure_never_a_verdict(tmp_path: Path, code: int) -> None:
    # Runs 2 and 3 execute in fresh extractions with no environment, so a cold sync is the
    # likeliest thing to hit the seam's wall-clock cap — and two timeouts read as "fails on
    # both", the worst wrong answer a tool feeding a ledger entry can give. A timed-out or
    # unlaunchable run is a `Failure` naming which run; no verdict is computed.
    # Mutation (declared): drop the short-circuit -> the timeout is scored as a failure and
    # `pytest.raises` reddens.
    root = _repo(tmp_path)
    with pytest.raises(Failure, match="head"):
        attribute(root, command="true", base="main", runner=_Coded({"head": code}))


@needs_git
def test_an_archive_an_export_rule_shrank_is_a_failure_and_not_a_smaller_tree(
    tmp_path: Path,
) -> None:
    # `git archive` honours the ARCHIVED tree's own `.gitattributes`, and `export-ignore` is
    # versioned like everything else in it — so runs 2 and 3 can quietly execute against trees
    # that are missing files the working tree has, and the verdict then answers a question
    # nobody asked. The guard compares each extraction against `git ls-tree -r --name-only REF`
    # and fails naming how many files are missing; the count is asserted, not merely that
    # something was raised, because a wrong count means the comparison is measuring the wrong
    # two sets.
    #
    # Mutation (declared): drop the comparison -> the extraction is one file short, all three
    # runs complete, a verdict is returned and `pytest.raises` reddens.
    root = _repo(tmp_path)
    (root / "secret.txt").write_text("kept out of the archive\n", encoding="utf-8")
    (root / ".gitattributes").write_text("secret.txt export-ignore\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "exported")
    with pytest.raises(Failure, match=r"missing 1 tracked file"):
        attribute(root, command="true", base="main", runner=_Coded({}))


@needs_git
def test_a_spaced_path_a_quoted_one_and_a_dangling_symlink_are_not_missing_files(
    tmp_path: Path,
) -> None:
    # Fix round 1, item 1. The export-rule guard fired on ordinary repositories and blamed a
    # `.gitattributes` rule that was not there. Three independent sources, one fixture:
    #
    #   * `set(listing.split())` broke `sub dir/a b.txt` into `sub`, `dir/a` and `b.txt` —
    #     three phantom entries, none of them on disk;
    #   * without `-z`, `ls-tree` renders `quo"te.txt` as `"quo\"te.txt"` and a non-ASCII name
    #     in octal escapes, so `splitlines()` alone would still have missed two of these;
    #   * `found` built with `p.is_file()` alone drops a tracked DANGLING symlink, because
    #     `is_file()` follows the link.
    #
    # Each was measured against the real `git` before the fix. The assertion is that the call
    # returns a verdict at all: this guard's failure mode is a `Failure` on a healthy tree, so
    # "it did not raise" is the whole claim, and the runner's tree snapshot pins that the
    # awkward names really were in the extraction rather than quietly absent from both sides.
    #
    # Mutation (declared): `-z` and the NUL split back to `split()` -> this reddens.
    root = _repo(tmp_path)
    (root / "sub dir").mkdir()
    (root / "sub dir" / "a b.txt").write_text("spaced\n", encoding="utf-8")
    (root / 'quo"te.txt').write_text("quoted\n", encoding="utf-8")
    (root / "ünïcode.txt").write_text("wide\n", encoding="utf-8")
    (root / "dangling.txt").symlink_to("nowhere-at-all")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "awkward names")
    runner = _Coded({})
    result = attribute(root, command="true", base="main", runner=runner)
    assert result.verdict == VERDICTS[4]
    head = runner.trees["head"]
    assert head["sub dir/a b.txt"] == "spaced\n"
    assert head['quo"te.txt'] == "quoted\n"


@needs_git
def test_a_tar_that_cannot_be_launched_is_a_finding_and_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fix round 1, item 2. Every external program is optional at runtime and a missing binary
    # is a reported finding: `gitenv.git_run` answers `(-1, "")` and `runner` answers
    # `Completed(NOT_FOUND, ...)`. The `tar` call was the one launch in this module with
    # nothing around it, so a machine without `tar` got `FileNotFoundError` out of a library
    # function, which only `cli.py`'s mapping caught — as an internal error, exit 2.
    #
    # A PATH holding `git` and nothing else, rather than an empty one: an empty PATH breaks
    # the merge-base first and the test would pass for the wrong reason, never reaching `tar`.
    # The assertion names `tar`, so a `Failure` raised anywhere else on the path does not
    # satisfy it. Mutation (declared): drop the `except OSError` -> `FileNotFoundError`
    # escapes and `pytest.raises(Failure)` reddens.
    git_binary = shutil.which("git")
    assert git_binary is not None
    root = _repo(tmp_path)
    only_git = tmp_path / "bin"
    only_git.mkdir()
    (only_git / "git").symlink_to(git_binary)
    monkeypatch.setenv("PATH", str(only_git))
    with pytest.raises(Failure, match="tar could not be run"):
        attribute(root, command="true", base="main", runner=_Coded({}))


@needs_git
def test_a_git_that_could_not_be_launched_is_not_reported_as_an_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fix round 1, item 6. `git_run` answers `(-1, "")` when the binary could not be launched,
    # and `-1` is a sentinel and not an exit status — rendered as one, the message read
    # "`git merge-base HEAD origin/main` exited -1; is origin/main fetched?", which sends a
    # reader to fetch a ref when the answer is that there is no git on this machine. The
    # assertion is on the cause, not on the exception type.
    root = _repo(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    with pytest.raises(Failure, match="git could not be run"):
        attribute(root, command="true", base="main", runner=_Coded({}))
