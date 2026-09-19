"""Attribute one failing command to the change or to the environment, with evidence.

Three runs, never two: the working tree as it is (1), HEAD's committed tree extracted into a
scratch directory (2), and the merge-base with the base branch extracted the same way (3).
Between (2) and (3) the only variable is the code; between (1) and (2) the only variable is
the environment — provided the command syncs its own environment, which is the caller's to
arrange and the reason the command is an argument.

Nothing here runs `git checkout`, `git stash` or `git reset`: `git archive` reads the object
database, and the working tree is read once and never written.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from keelline.errors import Failure, Refusal
from keelline.gitenv import git_run
from keelline.runner import NOT_FOUND, TIMED_OUT, Completed, Runner

VERDICTS = (
    "pre-existing: the failure is on the merge-base too, so it is not this change",
    "this change: HEAD fails and the merge-base passes",
    "this change fixed a pre-existing failure: HEAD passes and the merge-base fails",
    "environmental: HEAD passes when synced and fails in the working tree as it is",
    "not reproduced: all three runs passed",
)


@dataclass(frozen=True)
class Attribution:
    head_ambient: int
    head_clean: int
    base_clean: int
    base: str
    merge_base: str
    verdict: str


def _executed(run: str, done: Completed) -> int:
    """The exit code of a run that ran; a timed-out or unlaunchable one is never scored."""
    if done.code in (TIMED_OUT, NOT_FOUND):
        raise Failure(
            f"the {run} run did not execute (code {done.code}: "
            f"{done.stderr.strip() or 'no output'}); narrow the command, or check it launches"
        )
    return done.code


def _verdict(ambient: int, head: int, base: int) -> str:
    if head != 0 and base != 0:
        return VERDICTS[0]
    if head != 0 and base == 0:
        return VERDICTS[1]
    if head == 0 and base != 0:
        return VERDICTS[2]
    if ambient != 0:
        return VERDICTS[3]
    return VERDICTS[4]


def _extract(root: Path, ref: str, into: Path) -> None:
    """`git archive REF` into a sibling file, then `tar -x` into `into`.

    The archive is written BESIDE the extraction directory, never inside it: a repository
    with a root-level `tree.tar` would otherwise have the archive overwrite itself mid-read.
    `git archive` honours the archived tree's own `.gitattributes` (`export-ignore`,
    `export-subst`), which are versioned too — so the extracted listing is compared to
    `git ls-tree -r --name-only REF`, and a difference is a `Failure` naming the attribute
    rather than a silently smaller tree steering the verdict.
    """
    into.mkdir()
    archive = into.parent / f"{into.name}.tar"
    code, _ = git_run(root, "archive", "--format=tar", "-o", str(archive), ref, timeout=120)
    if code != 0:
        raise Failure(f"`git archive {ref}` exited {code}; nothing was extracted")
    done = subprocess.run(  # noqa: S603
        ["tar", "-xf", str(archive)],  # noqa: S607 - PATH on purpose: the machine owner's tar
        cwd=into,
        capture_output=True,
        check=False,
    )
    archive.unlink()
    if done.returncode != 0:
        raise Failure(f"extracting {ref} exited {done.returncode}")
    code, listing = git_run(root, "ls-tree", "-r", "--name-only", ref)
    expected = set(listing.split())
    found = {str(p.relative_to(into)) for p in into.rglob("*") if p.is_file()}
    if code == 0 and expected - found:
        raise Failure(
            f"{ref}'s archive is missing {len(expected - found)} tracked file(s) — a "
            f"`.gitattributes` export rule in that tree; this tool cannot compare it"
        )


def attribute(root: Path, *, command: str, base: str, runner: Runner) -> Attribution:
    if base.startswith("-"):
        raise Refusal("--base must name a ref, not an option")
    code, merge_base = git_run(root, "merge-base", "HEAD", base)
    merge_base = merge_base.strip()
    if code != 0 or not merge_base:
        raise Failure(f"`git merge-base HEAD {base}` exited {code}; is {base} fetched?")
    ambient = _executed("working tree", runner.run(["sh", "-c", command], root))
    with tempfile.TemporaryDirectory(prefix="keelline-attribute-") as scratch:
        head = Path(scratch) / "head"
        merge = Path(scratch) / "base"
        _extract(root, "HEAD", head)
        _extract(root, merge_base, merge)
        head_clean = _executed("head", runner.run(["sh", "-c", command], head))
        base_clean = _executed("base", runner.run(["sh", "-c", command], merge))
    return Attribution(
        ambient, head_clean, base_clean, base, merge_base, _verdict(ambient, head_clean, base_clean)
    )
