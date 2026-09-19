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
