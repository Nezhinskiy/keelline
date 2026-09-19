#!/usr/bin/env python3
"""Apply each mutation `mutations.toml` declares and check that the named tests go red.

The plans ask that "every new assertion ships with the mutation that reddens it, or a sentence
saying why none exists", and until now those mutations existed only as English sentences inside
multi-thousand-line plan documents. A contributor could satisfy the rule only by hand-editing
source and reverting, and a reviewer had no way to check they had.

This is not a general mutation tester — `mutmut` is, and is far too slow to gate a pull request
on. It is the curated set: the guards whose *load-bearingness* has to be proven rather than
merely covered, which is exactly the distinction that let `fsops.open_within` be fully covered
by twelve tests and still contain nothing.

Each entry names one file, one exact substring to replace, and the tests that must fail when it
is. A mutation that survives — the tests still pass with the guard broken — is a finding, and so
is one whose `before` no longer appears in the file, because that means the assertion and the
line it is about have drifted apart.

Usage:

    uv run python scripts/mutation_oracle.py            # every declared mutation
    uv run python scripts/mutation_oracle.py fsops      # only those whose name or file matches

Every mutation is applied to a throwaway worktree of `HEAD`; the working tree is never written.

Exit codes match the rest of the project: 0 all held, 1 findings.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECLARATION = ROOT / "mutations.toml"


@dataclass(frozen=True)
class Mutation:
    name: str
    file: Path
    before: str
    after: str
    reddens: tuple[str, ...]


def declared() -> list[Mutation]:
    raw = tomllib.loads(DECLARATION.read_text(encoding="utf-8"))
    return [
        Mutation(
            name=str(entry["name"]),
            file=ROOT / str(entry["file"]),
            before=str(entry["before"]),
            after=str(entry["after"]),
            reddens=tuple(str(t) for t in entry["reddens"]),
        )
        for entry in raw.get("mutation", [])
    ]


class WorktreeUnavailable(RuntimeError):
    """`git worktree add` did not produce a checkout; the message is git's own stderr."""


@contextlib.contextmanager
def scratch_checkout() -> Iterator[Path]:
    """A detached worktree of HEAD under a temporary directory, removed afterwards.

    The oracle proves HEAD and never the working tree (DC1). `--detach` so no branch is
    created or moved; `worktree remove --force` and `rmtree` in the `finally` so a run that
    was interrupted mid-mutation leaves nothing behind but a prunable entry, which the next
    `git worktree prune` clears. The parent directory is created by `mkdtemp` and the tree
    goes one level below it, because `git worktree add` refuses a path that already exists.
    """
    parent = Path(tempfile.mkdtemp(prefix="keelline-oracle-"))
    tree = parent / "tree"
    added = subprocess.run(  # noqa: S603
        ["git", "-C", str(ROOT), "worktree", "add", "--detach", "--quiet", str(tree), "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if added.returncode != 0:
        shutil.rmtree(parent, ignore_errors=True)
        raise WorktreeUnavailable(added.stderr.strip() or f"exit {added.returncode}")
    try:
        yield tree
    finally:
        subprocess.run(  # noqa: S603
            ["git", "-C", str(ROOT), "worktree", "remove", "--force", str(tree)],  # noqa: S607
            capture_output=True,
            check=False,
        )
        shutil.rmtree(parent, ignore_errors=True)


@dataclass(frozen=True)
class Outcome:
    """One pytest run, as the two facts the oracle reasons about.

    `code` alone is not enough, and that is the whole point of this type. Exit 0 is "nothing
    failed", which a run of zero tests satisfies just as well as a run of twenty — so an
    oracle that reads only the exit code cannot tell a green assertion from an absent one.
    `executed` is how many tests actually ran and reported a result, taken from pytest's own
    JUnit report rather than parsed out of its prose.
    """

    code: int
    executed: int

    @property
    def passed(self) -> bool:
        return self.code == 0 and self.executed > 0


def _executed(report: Path) -> int:
    """How many tests ran and were not skipped, from pytest's own JUnit XML.

    Machine-readable on purpose. The alternative — looking for the word "passed" in `-q`
    output — makes the oracle's own correctness depend on the wording of a summary line, and
    this file's history is a run of defects where the oracle could not tell one state from
    another. A report pytest never wrote (a usage error, which is exactly what a mistyped test
    id produces) counts as zero, which is the honest answer and the fail-closed one.
    """
    if not report.is_file():
        return 0
    try:
        # `S314`, with the reasoning where a reviewer sees it, as the two `subprocess` sites
        # below already do. This document is not untrusted input: it was written moments ago by
        # the pytest this process launched, into a `TemporaryDirectory` this process created,
        # and it is read before that directory is removed. Nothing a repository authors reaches
        # it except through pytest's own attribute escaping.
        root = ElementTree.parse(report).getroot()  # noqa: S314
    except ElementTree.ParseError:
        return 0
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    return sum(int(suite.get("tests", 0)) - int(suite.get("skipped", 0)) for suite in suites)


def _run(targets: tuple[str, ...], cwd: Path) -> Outcome:
    """Run only the named tests, against a bytecode cache that cannot be stale.

    `PYTHONPYCACHEPREFIX` at a fresh empty directory, and this is not belt-and-braces — it is
    load-bearing, and CI found that out. A `.pyc` header records the source's mtime **truncated
    to whole seconds**, so two writes to one file inside the same second that leave it the same
    size are indistinguishable to the import system. Two of the mutations below happen to change
    `memory/notes.py` by exactly the same 20 bytes each; on a fast runner the second one was written
    within a second of the first one's restore, Python reused the bytecode compiled under the
    *first* mutation, and the second was reported as surviving when it does not.

    An oracle whose own failures look exactly like findings is worse than no oracle, so the
    cache is made unusable rather than merely discouraged: `PYTHONDONTWRITEBYTECODE` keeps the
    fresh directory empty, and an empty cache directory means every module is compiled from the
    source actually on disk.
    """
    with tempfile.TemporaryDirectory(prefix="keelline-oracle-cache-") as cache:
        report = Path(cache) / "report.xml"
        # The scratch checkout's `src` goes FIRST: the editable install of the main checkout is
        # on `sys.path` through site-packages, and PYTHONPATH is the only entry that precedes
        # it. Without this the named tests import the unmutated modules and every mutation
        # "survives" — measured before the line was written, by the test that pins it.
        inherited = os.environ.get("PYTHONPATH", "")
        pythonpath = str(cwd / "src") + (os.pathsep + inherited if inherited else "")
        done = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-B",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "--no-header",
                f"--junit-xml={report}",
                *targets,
            ],
            cwd=cwd,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PYTHONPATH": pythonpath,
                "PYTHONPYCACHEPREFIX": cache,
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        return Outcome(done.returncode, _executed(report))


def _check(mutation: Mutation, tree: Path) -> str | None:
    """`None` when the mutation was caught; the finding otherwise.

    Every read and write lands in `tree`, a throwaway checkout of HEAD, at the same path
    relative to `ROOT` the entry names (DC1). The working tree is never touched.

    **The clean-tree run comes first, and it is not a formality.** Without it this function
    read "the named tests did not pass" as "the mutation was caught" — and a mistyped test id
    makes pytest exit 4, which is not zero, which read as caught. So an entry could name
    `test_this_does_not_exist`, the oracle would print `caught`, CI would go green, and the
    guard it claims to prove would be provably unprotected. An oracle whose own failures look
    exactly like its successes is worse than no oracle.

    A run of zero tests is the same hole wearing a different face, so `Outcome.passed`
    demands that something actually ran: an entry whose tests are all skipped in this
    environment proves nothing here, and says so rather than banking the skip as a proof.
    """
    subject = tree / mutation.file.relative_to(ROOT)
    if not subject.is_file():
        return f"{mutation.file.relative_to(ROOT)} does not exist"
    original = subject.read_text(encoding="utf-8")
    occurrences = original.count(mutation.before)
    if occurrences == 0:
        return (
            "its `before` line is not in the file any more — the assertion and the line it is "
            "about have drifted apart, so update the entry or delete it"
        )
    if occurrences > 1:
        return f"its `before` line appears {occurrences} times; make it unique"
    clean = _run(mutation.reddens, tree)
    if not clean.passed:
        return (
            f"{', '.join(mutation.reddens)} did not pass on a clean tree "
            f"(pytest exited {clean.code}, {clean.executed} test(s) ran) — so nothing here can "
            "tell a mutation this entry caught from one it never tested; fix or rename them"
        )
    subject.write_text(original.replace(mutation.before, mutation.after), encoding="utf-8")
    try:
        mutated = _run(mutation.reddens, tree)
    finally:
        subject.write_text(original, encoding="utf-8")
    if mutated.code == 0:
        return f"survived — {', '.join(mutation.reddens)} still passed with the guard broken"
    return None


def _uncommitted(files: set[Path]) -> str | None:
    """`None` when every file is committed as it stands; the refusal otherwise.

    The oracle proves HEAD in a scratch checkout, so an uncommitted edit is simply work this
    run cannot see: the entry would be proved against the committed bytes while its author
    reads the result as being about the ones on screen. `main` therefore passes **both** the
    mutated files and the test files every selected entry's `reddens` names — an uncommitted
    edit to a test is as invisible to a HEAD checkout as one to a source, and the first draft
    of this guard swept only the sources.

    **"Could not ask" is not "clean"**: it
    read any non-zero `git` exit as a clean tree, which is precisely the state an unpacked
    sdist is in (`scripts/**` and `mutations.toml` ship in it, and it is not a checkout) and
    the state a broken `git` installation produces. `git status` exits 128 outside a
    repository, so the one arrangement with no way to recover a clobbered file was the one
    where the guard stood down.

    A `git` that cannot be launched at all raises rather than returning, and is caught here for
    the same reason: an oracle that cannot establish the precondition refuses, it does not
    proceed.
    """
    try:
        status = subprocess.run(  # noqa: S603
            ["git", "status", "--porcelain", "--", *sorted(str(f) for f in files)],  # noqa: S607
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return (
            f"`git` could not be run ({exc}), so this cannot tell whether the files it is "
            "about to rewrite hold uncommitted work — refusing rather than risking it"
        )
    if status.returncode != 0:
        detail = status.stderr.strip() or f"exit {status.returncode}"
        return (
            f"`git status` could not answer here ({detail}), so this cannot tell whether the "
            "files it is about to rewrite hold uncommitted work — refusing rather than risking "
            "it. Run the oracle from a git checkout of the project"
        )
    if status.stdout.strip():
        return (
            "refusing: these files have uncommitted changes, and the oracle proves HEAD in a "
            "scratch checkout, so an edit here is work this run cannot see — commit first:\n"
            + status.stdout
        )
    return None


def main(argv: list[str]) -> int:
    pattern = argv[0] if argv else ""
    mutations = [
        m for m in declared() if not pattern or pattern in m.name or pattern in str(m.file)
    ]
    if not mutations:
        print(f"no mutation matches {pattern!r}", file=sys.stderr)
        return 1
    named_tests = {ROOT / target.split("::", 1)[0] for m in mutations for target in m.reddens}
    watched = {m.file for m in mutations} | {path for path in named_tests if path.is_file()}
    dirty = _uncommitted(watched)
    if dirty is not None:
        print(dirty, file=sys.stderr)
        return 1

    findings: list[str] = []
    try:
        with scratch_checkout() as tree:
            for mutation in mutations:
                finding = _check(mutation, tree)
                mark = "caught " if finding is None else "FINDING"
                print(f"{mark}  {mutation.name}")
                if finding is not None:
                    findings.append(f"{mutation.name}: {finding}")
    except WorktreeUnavailable as exc:
        print(
            f"could not create a scratch worktree of HEAD ({exc}); the oracle never mutates "
            "the working tree, so there is nothing to fall back to",
            file=sys.stderr,
        )
        return 1
    print()
    if findings:
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(f"\n{len(findings)} of {len(mutations)} mutations were not caught", file=sys.stderr)
        return 1
    print(f"all {len(mutations)} mutations were caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
