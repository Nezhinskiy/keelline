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

import ast
import contextlib
import os
import shutil
import signal
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
# Where scratch checkouts are made and where the sweep looks for leaked ones. A module-level
# name rather than a `gettempdir()` call at each site, for the reason `ROOT` is one: this
# module deletes directories, and its own tests have to be able to aim both halves somewhere
# harmless. `tests/scripts/test_mutation_oracle.py` redirects this beside `ROOT` — before it
# did, every run of that module swept the developer's real temporary directory, which is a
# thing the suite must not touch and which would have destroyed a concurrent oracle's checkout.
TEMPDIR = Path(tempfile.gettempdir())


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


class ConcurrentRun(RuntimeError):
    """Another oracle holds the lock; the message names it and the process that does."""


def _holder(lock: Path) -> str | None:
    """What is written in the lock file if the process that wrote it is still alive.

    **Unreadable is treated as alive, and that is the conservative direction.** The failure this
    lock prevents is one run deleting another's checkout, and the cost of being wrong the other
    way is a message telling a person which file to remove. A lock whose contents this process
    cannot parse is far more likely to be a live run on a filesystem doing something odd than a
    dead one, so it refuses and says where to look.
    """
    try:
        content = lock.read_text(encoding="utf-8").strip()
    except OSError:
        return "a process this one cannot ask about"
    pid = content.partition(" ")[0]
    if not pid.isdigit():
        return content or "a process this one cannot name"
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        # Alive and owned by somebody else, which is still alive.
        return content
    except OSError:
        return content
    return content


@contextlib.contextmanager
def single_run(tempdir: Path | None = None) -> Iterator[Path]:
    """Hold the one-oracle-at-a-time lock, or refuse naming what holds it.

    **`sweep_stale_scratch` assumes a single writer and nothing enforced it.** Its own docstring
    states the assumption — "a second run started while the first is working would sweep the
    first's checkout out from under it" — and that is exactly what happened during the wave-3
    refactor pass's review: a filtered run started beside an unfiltered one removed its checkout,
    and every
    mutation after that point reported `FINDING`. 138 of them, all false, on a tree with nothing
    wrong with it. A comment naming a hazard does not stop the hazard; this does.

    `O_CREAT | O_EXCL` is the whole mechanism: the create either wins or raises, with no window
    between the test and the write. A lock whose writer has died is taken over rather than
    obeyed, because a `SIGKILL` runs no `finally` and a stale lock that refused for ever would
    be a worse failure than the one this prevents. The retry is bounded at one: losing the race
    twice means another run really is starting, and that is a refusal rather than a spin.
    """
    lock = (tempdir or TEMPDIR) / LOCK_NAME
    mine = f"{os.getpid()} {ROOT}"
    for attempt in range(2):
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            holder = _holder(lock)
            if holder is not None:
                raise ConcurrentRun(
                    f"another mutation oracle is running ({holder}); this one refuses rather "
                    f"than sweeping its scratch checkout out from under it. Wait for it, or "
                    f"remove {lock} if you are sure it is gone"
                ) from None
            if attempt:
                raise ConcurrentRun(
                    f"{lock} changed hands while a stale one was being cleared; another run is "
                    f"starting"
                ) from None
            lock.unlink(missing_ok=True)
            continue
        with os.fdopen(handle, "w", encoding="utf-8") as writing:
            writing.write(mine)
        try:
            yield lock
        finally:
            # Only if it is still ours: a run that took this one over as stale owns it now, and
            # unlinking its lock on the way out would be this function doing the very thing it
            # was written to stop.
            try:
                held = lock.read_text(encoding="utf-8").strip()
            except OSError:
                held = ""
            if held == mine:
                lock.unlink(missing_ok=True)
        return


SCRATCH_PREFIX = "keelline-oracle-"
# The one-run-at-a-time lock, beside the scratch checkouts it exists to protect. A **file** and
# not a directory, which is what keeps it out of `sweep_stale_scratch`'s own housekeeping: that
# walk globs this prefix and removes directories, and the `is_dir()` arm is what spares this.
# Asserted rather than assumed — `tests/scripts/test_mutation_oracle.py` holds the sweep to it.
LOCK_NAME = f"{SCRATCH_PREFIX}lock"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(ROOT), *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )


def sweep_stale_scratch(keep: Path | None = None, *, tempdir: Path | None = None) -> list[str]:
    """Drop every leaked scratch checkout but this run's, and return what was dropped.

    **`git worktree prune` does not clear these, and the docstring that said it did was wrong
    in both halves.** `prune` only drops entries whose directory is *gone*, and an interrupted
    run leaves the `mkdtemp` tree standing — so the registration survived every prune, the
    commit stayed pinned against `git gc`, and the tree stayed on disk. One was found in the
    development repository during review: 6.5 MB, and `git worktree prune --dry-run -v` printed
    nothing about it. Because the leaked trees are checkouts of this repository they also join
    `hooks/run-hook.sh`'s `list_checkouts` containment set, which is the part that is not
    merely untidy.

    The order matters: `worktree remove --force` first so git forgets the registration, then
    `rmtree` for anything `remove` declined, then `prune` to collect whatever is now missing a
    directory. Failures are not raised — this is housekeeping at the top of a run, and a
    temporary directory another user owns is not this run's business.

    **The cost, stated rather than hidden: this assumes one oracle at a time.** A second run
    started while the first is working would sweep the first's checkout out from under it. That
    is the same single-writer assumption DC1 already makes — the scratch checkout exists so that
    two oracles, or an oracle beside an editor, cannot interleave writes over one file — and CI
    runs exactly one. The sweep is at the *top* of `main` and never again, so nothing a live run
    creates afterwards is in reach of it.
    """
    dropped: list[str] = []
    listing = _git("worktree", "list", "--porcelain")
    registered = [
        Path(line[len("worktree ") :])
        for line in listing.stdout.splitlines()
        if line.startswith("worktree ")
    ]
    for tree in registered:
        if tree.name != "tree" or not tree.parent.name.startswith(SCRATCH_PREFIX):
            continue
        if keep is not None and tree == keep:
            continue
        _git("worktree", "remove", "--force", str(tree))
        shutil.rmtree(tree.parent, ignore_errors=True)
        dropped.append(str(tree.parent))
    # And the trees no `git worktree` entry points at any more: `_run`'s `TemporaryDirectory`
    # leaks the same way on a kill, under the same prefix.
    #
    # `tempdir` overrides `TEMPDIR` for one call; both exist because this function deletes
    # directories and a test has to be able to aim it somewhere harmless. With `gettempdir()`
    # hard-coded here, every run of `tests/scripts/test_mutation_oracle.py` swept the
    # developer's real temporary directory — measured with a canary planted there, which the
    # suite removed — and a real oracle running at that moment would have lost its checkout.
    for stale in (tempdir or TEMPDIR).glob(f"{SCRATCH_PREFIX}*"):
        if keep is not None and keep.parent == stale:
            continue
        if str(stale) in dropped or not stale.is_dir():
            continue
        shutil.rmtree(stale, ignore_errors=True)
        dropped.append(str(stale))
    _git("worktree", "prune")
    return dropped


@contextlib.contextmanager
def scratch_checkout() -> Iterator[Path]:
    """A detached worktree of HEAD under a temporary directory, removed afterwards.

    The oracle proves HEAD and never the working tree (DC1). `--detach` so no branch is
    created or moved. The parent directory is created by `mkdtemp` and the tree goes one level
    below it, because `git worktree add` refuses a path that already exists.

    **Cleanup, which is the half this used to get wrong.** The `finally` removes the *tree*
    before asking git to drop the registration, so an entry whose `worktree remove` fails is
    at least left prunable rather than pinned for ever; `prune` then collects it. A `SIGTERM`
    is turned into `SystemExit` so that a terminate runs the `finally` at all — without the
    handler, the ordinary way CI and an interrupted agent stop a process left everything
    behind. `SIGKILL` cannot be caught by anything, which is what `sweep_stale_scratch` at the
    top of `main` is for.
    """
    parent = Path(tempfile.mkdtemp(prefix=SCRATCH_PREFIX, dir=TEMPDIR))
    tree = parent / "tree"
    added = _git("worktree", "add", "--detach", "--quiet", str(tree), "HEAD")
    if added.returncode != 0:
        shutil.rmtree(parent, ignore_errors=True)
        raise WorktreeUnavailable(added.stderr.strip() or f"exit {added.returncode}")
    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, _terminate)
    try:
        yield tree
    finally:
        signal.signal(signal.SIGTERM, previous)
        # `rmtree` BEFORE `worktree remove`: git refuses to remove a worktree it considers
        # dirty, and a run interrupted mid-mutation leaves exactly that. Removing the directory
        # first makes the entry prunable whatever `remove` then says.
        shutil.rmtree(parent, ignore_errors=True)
        _git("worktree", "remove", "--force", str(tree))
        _git("worktree", "prune")


def _terminate(signum: int, frame: object) -> None:
    """A terminate becomes an exception, so every `finally` on the stack runs."""
    raise SystemExit(f"terminated by signal {signum}")


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
    """How many tests ran and reported a result, from pytest's own JUnit XML.

    Machine-readable on purpose. The alternative — looking for the word "passed" in `-q`
    output — makes the oracle's own correctness depend on the wording of a summary line, and
    this file's history is a run of defects where the oracle could not tell one state from
    another. A report pytest never wrote (a usage error, which is exactly what a mistyped test
    id produces) counts as zero, which is the honest answer and the fail-closed one.

    **`errors` are subtracted as well as `skipped`, and that is the whole of the count's
    meaning.** A module that cannot be imported still produces a JUnit report with one
    `<testcase>` in it carrying an `<error>`, so `tests - skipped` came to 1 for a run in which
    the named test never executed — measured: `code 4 executed 1`. The question this number
    answers is "did the assertion get to run", and a collection error, a fixture that raised
    and a mistyped id are all "no". Subtracting them is what lets `_check` tell a mutation that
    reddened a guard from one that stopped the guard's test from running at all.
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
    return sum(
        int(suite.get("tests", 0)) - int(suite.get("skipped", 0)) - int(suite.get("errors", 0))
        for suite in suites
    )


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
    with tempfile.TemporaryDirectory(prefix=f"{SCRATCH_PREFIX}cache-", dir=TEMPDIR) as cache:
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


def anchor_finding(text: str, before: str) -> str | None:
    """Why `before` cannot anchor a mutation in `text`, or `None` when it occurs exactly once.

    Shared by `_check`, which meets it inside a full run, and by the suite's static test over
    `mutations.toml`, which meets it at the commit that causes it. Before the static test, an
    entry whose line a task rewrote was noticed only by an unfiltered run twenty minutes later
    — five times on one branch, once after the commit, which then needed a history rewrite.
    """
    occurrences = text.count(before)
    if occurrences == 0:
        return (
            "its `before` line is not in the file any more — the assertion and the line it is "
            "about have drifted apart, so update the entry or delete it"
        )
    if occurrences > 1:
        return f"its `before` line appears {occurrences} times; make it unique"
    return None


def undefined_tests(reddens: tuple[str, ...], root: Path) -> list[str]:
    """The ids in `reddens` whose file does not define the function they name.

    Read from the syntax tree, not from a pytest collection: the whole of `mutations.toml` is
    checked in well under a second, which is what lets it run with the suite. A parametrized
    id's bracketed part is not checked here — only a collection can see parameter ids — and
    stays the clean-tree run's to catch, as it always was.
    """
    missing: list[str] = []
    parsed: dict[Path, ast.Module | None] = {}
    for node_id in reddens:
        path, *names = node_id.split("[", 1)[0].split("::")
        source = root / path
        if source not in parsed:
            parsed[source] = (
                ast.parse(source.read_text(encoding="utf-8")) if source.is_file() else None
            )
        scope: ast.AST | None = parsed[source]
        for name in names:
            body = getattr(scope, "body", [])
            scope = next(
                (
                    node
                    for node in body
                    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                    and node.name == name
                ),
                None,
            )
        if scope is None or not names:
            missing.append(node_id)
    return missing


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
    anchor = anchor_finding(original, mutation.before)
    if anchor is not None:
        return anchor
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
    # **The clean run's reasoning, applied to the mutated run, which is the half that was
    # left open.** The paragraphs above argue at length that an exit code alone cannot tell a
    # green assertion from an absent one — and then judged the mutated run by `mutated.code`
    # alone, computing `mutated.executed` and discarding it. A mutation that makes the module
    # unimportable exits 2 from a collection error, which is not zero, which read as `caught`
    # although the named test never ran. Demonstrated on a synthetic entry whose `after` was
    # `import a_module_that_does_not_exist`: `caught`, `all 1 mutations were caught`, exit 0.
    #
    # Not an equality with `clean.executed`, because a guard that legitimately stops one
    # parametrised case from being generated is a real thing; zero is the line, and a count
    # that fell is reported so a reader can judge it.
    if mutated.executed == 0:
        return (
            f"the mutation stopped {', '.join(mutation.reddens)} from running at all "
            f"({clean.executed} test(s) ran on the clean tree, 0 with the mutation applied) "
            "rather than reddening them — pytest's exit code says only that something went "
            "wrong, and this entry proves nothing about the guard"
        )
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

    # The lock is taken before the sweep and held to the end, because the sweep is the
    # destructive half: `sweep_stale_scratch` removes every scratch checkout but this run's, and
    # "but this run's" is only safe while there is one run. A second oracle refuses here rather
    # than deleting the first one's tree.
    try:
        with single_run():
            return _prove(mutations)
    except ConcurrentRun as exc:
        print(exc, file=sys.stderr)
        return 1


def _prove(mutations: list[Mutation]) -> int:
    """Sweep, then apply every mutation in one scratch checkout. Called holding the lock."""
    # Housekeeping before the run, not after it: a `SIGKILL` runs no `finally`, so the entries
    # an earlier killed run left behind are cleared here or never. `git worktree prune` alone
    # does not do it — it only drops entries whose directory is gone, and these leave theirs.
    swept = sweep_stale_scratch()
    for leaked in swept:
        print(f"swept a leaked scratch checkout: {leaked}", file=sys.stderr)

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
