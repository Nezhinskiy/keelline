"""Attribute one failing command to the change or to the environment, with evidence.

Three runs, never two: the working tree as it is (1), HEAD's committed tree extracted into a
scratch directory (2), and the merge-base with the base branch extracted the same way (3).
Between (2) and (3) the only variable is the code; between (1) and (2) the only variable is
the environment — provided the command syncs its own environment, which is the caller's to
arrange and the reason the command is an argument.

Nothing here runs `git checkout`, `git stash` or `git reset`: `git archive` reads the object
database, and this module never writes the working tree or moves the checkout between
commits. Run 1 does execute the caller's command *in* the working tree, so whatever that
command writes there it writes — the guarantee is about this tool, not about that run.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from keelline.errors import Failure, Refusal
from keelline.gitenv import git_run, scrubbed_env
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
    `git ls-tree -r --name-only REF`, and a difference is a `Failure` naming the likely cause
    rather than a silently smaller tree steering the verdict.

    **Both sides of that comparison are built the pedantic way, because every casual version
    of it made the check fire on ordinary repositories.** `-z` and a split on NUL, never
    `split()` and never `splitlines()`: `split()` breaks `sub dir/a b.txt` into three phantom
    entries, and plain `splitlines()` survives that but not git's own quoting — without `-z`,
    `ls-tree` renders a name carrying a quote or a non-ASCII byte as `"quo\"te.txt"` and
    `"\303\274n..."`, neither of which is the name on disk.

    And presence is **asked of each expected name**, never inferred from a walk of the
    extraction. A walk that kept files and symlinks still answered "missing" for a submodule
    gitlink, which `git archive` materialises as an empty directory and which is therefore
    neither — measured, so every submodule-bearing repository got this `Failure`. `exists()`
    answers for that directory and `is_symlink()` for a tracked dangling link, whose own
    special case disappears into the same line.
    """
    into.mkdir()
    archive = into.parent / f"{into.name}.tar"
    code, _ = git_run(root, "archive", "--format=tar", "-o", str(archive), ref, timeout=120)
    if code != 0:
        raise Failure(f"`git archive {ref}` exited {code}; nothing was extracted")
    try:
        done = subprocess.run(  # noqa: S603
            # PATH on purpose: the machine owner's tar. `env=` for the same reason every other
            # subprocess in this tree scrubs -- `TAR_OPTIONS` and `TAPE` in the ambient
            # environment otherwise reach an extraction whose contents decide a verdict.
            ["tar", "-xf", str(archive)],  # noqa: S607
            cwd=into,
            capture_output=True,
            check=False,
            env=scrubbed_env(),
        )
    # A missing binary is a reported finding, never a traceback (the global constraints make
    # every external program optional): `gitenv.git_run` answers `(-1, "")` on an `OSError` and
    # `runner` answers `Completed(NOT_FOUND, ...)`; this is the same rule for `tar`.
    except OSError as exc:
        raise Failure(f"extracting {ref}: tar could not be run ({exc})") from None
    archive.unlink()
    if done.returncode != 0:
        raise Failure(f"extracting {ref} exited {done.returncode}")
    try:
        code, listing = git_run(root, "ls-tree", "-r", "--name-only", "-z", ref)
    # `-z` is what makes this reachable, so it arrived with the fix above: without it `ls-tree`
    # octal-escapes a non-ASCII name and the answer is always ASCII, and with it the bytes come
    # through raw. `git_run` runs with `text=True` and strict decoding while catching only
    # `OSError` and `SubprocessError`, so a tracked name this process's locale cannot decode —
    # a latin-1 filename committed on Linux, any non-ASCII name under an uncoerced `C` locale —
    # raised `UnicodeDecodeError` out of a library function. Contained at the call site and not
    # in `git_run`: its other callers ask for a sha or a config value and never for raw bytes,
    # and widening a shared seam for one caller's new appetite is how a seam stops meaning
    # anything.
    #
    # A listing that cannot be read is no listing at all, which is exactly what the `code != 0`
    # arm below already does with one that could not be produced. Skipping is the right answer
    # rather than a cop-out: this comparison exists to catch an export rule, it cannot answer
    # that question about a listing it never read, and raising on it would be one more
    # over-eager `Failure` on a healthy tree — the defect this whole comparison has now
    # produced in three separate shapes.
    except UnicodeDecodeError:
        code, listing = -1, ""
    expected = {name for name in listing.split("\0") if name}
    missing = [
        name for name in expected if not (into / name).exists() and not (into / name).is_symlink()
    ]
    if code == 0 and missing:
        raise Failure(
            f"{ref}'s archive is missing {len(missing)} tracked file(s); the likely "
            f"cause is a `.gitattributes` export rule in that tree, and this tool cannot "
            f"compare a tree it did not get whole"
        )


def attribute(root: Path, *, command: str, base: str, runner: Runner) -> Attribution:
    if base.startswith("-"):
        raise Refusal("--base must name a ref, not an option")
    code, merge_base = git_run(root, "merge-base", "HEAD", base)
    merge_base = merge_base.strip()
    # `git_run`'s own sentinel for "the binary could not be launched at all", which is not an
    # exit code and must not be rendered as one: `exited -1; is origin/main fetched?` sends a
    # reader to fetch a ref when the answer is that there is no git here.
    if code == -1:
        raise Failure(f"git could not be run, so `merge-base HEAD {base}` never executed")
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
