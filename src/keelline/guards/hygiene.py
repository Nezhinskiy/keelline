"""Name what could have falsified a red test run, before the diff is blamed.

Two environment faults produce a red run that no baseline A/B can attribute, because both
halves of the A/B run inside the same fault: uncommitted work in the tree (the measurement
describes a tree nobody is merging) and bytecode newer than its source (the interpreter
imports a build that predates a fix on disk -- deterministically, in the shape of the very
defect the test pins). Both have cost real time: the first twice in one branch's retro, the
second a high-severity ledger entry rejected as a stale cache.

Warn-only by construction: the tool has already run, and the verdict this guards is the
human's next sentence, not the command. Once per context, which the dispatcher's `once_key`
owns (see `hooks.py` for what that currently means).

Matching an actual pytest invocation, not the six letters "pytest" appearing anywhere in the
command text, uses the shared scanner's tokens and segments: an argv0-anchored check per
segment, resolved past a leading shell assignment (`FOO=1 pytest`) and a small, exact
wrapper-prefix set (`env cmd`, `uv run cmd`). Under-reporting an unrecognised launcher is the
safe direction for a warn-only note, so the set only grows when a real shape is reproduced.

Which harness field says a run was red is documented rather than assumed: the Claude Code hooks
reference gives the Bash `tool_response` as `stdout`, `stderr`, `interrupted` and `isImage`
with no exit code, and a non-zero exit arriving on `PostToolUseFailure` as
`error: "Exit code N\\n…"`. `red_exit` reads both that shape and a `tool_response.exit_code`,
so the notice is keyed on whichever the harness sends rather than on a field one lacks.

Nothing a repository authored leaves this module. The notice carries the fixed sentences below
and counts this module computed; a `ledger.code_roots` entry is walked and never printed.
"""

from __future__ import annotations

import importlib.util
import re
import struct
import subprocess
from collections.abc import Iterable, Mapping
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from keelline.gitenv import scrubbed_env
from keelline.guards import bashscan
from keelline.guards.roots import contained_roots

if TYPE_CHECKING:
    from keelline.config.schema import Config

PYTEST = "pytest"
_PYTHON_ARGV0_PREFIX = "python"
# Anchored TWICE, redundantly: the `\A` here and the `.match` at the call site each pin the read
# to index 0, so removing either one alone is a no-op -- measured, in both directions -- and only
# removing BOTH unanchors it. Do not read one of them as dead weight: unanchored, a number is
# read out of arbitrary captured stderr, and a line of pytest output that merely quotes an exit
# code is then taken for the run's own. The documented shape puts `Exit code N` at the very
# START of `error`, which is what the pair is protecting.
_EXIT_CODE_ERROR = re.compile(r"\AExit code (\d+)")
# Its own named cap, not `gitenv.GIT_TIMEOUT_SECONDS`: that constant covers "local,
# argument-free, read-only" queries, and `git status --porcelain` walks the worktree. A
# timeout here is `None`, "could not answer", which `test hygiene` turns into a refusal.
STATUS_TIMEOUT_SECONDS = 20
# PEP 552: every .pyc opens with a 4-byte magic, then a 4-byte little-endian flags word, then
# four more bytes whose MEANING is decided by bit 0 of those flags.
#
# Bit 0 clear -- timestamp-based, the default -- makes them the source's mtime as a uint32, the
# value CPython itself compares against the source's current mtime. That is the only comparison
# that agrees with the interpreter's own staleness verdict, which is why it is the one made here
# and not a `pyc mtime > source mtime` on the filesystem.
#
# Bit 0 SET -- hash-based -- makes them the first half of the source's hash instead, and nothing
# in them can be compared to an mtime at all: doing so declares every such file stale, forever.
# That is not a rare shape. `py_compile` switches to it on its own whenever `SOURCE_DATE_EPOCH`
# is set in the environment, and `compileall --invalidation-mode checked-hash` asks for it
# outright, so a reproducible build produces a whole tree of them. A hash-based `.pyc` is
# therefore NOT JUDGED: under-reporting is this module's safe direction throughout, and telling
# somebody their bytecode predates a fix -- delete `__pycache__` and re-run -- when it is in
# fact current is exactly the false alarm that direction exists to avoid.
#
# The MAGIC decides whether this interpreter would ever open the file at all, and reading past a
# foreign one is the same class of defect as reading a hash-based header as an mtime. A
# `__pycache__` accumulates one `.pyc` per interpreter tag and nothing removes the old ones, so
# a `mod.cpython-311.pyc` left by a 3.11 run sits beside the current tag's file forever,
# recording the source mtime as of THAT run. Any edit since makes it mismatch -- while the
# bytecode the running interpreter actually imports is fresh. Measured on a tree whose current
# bytecode had just been compiled: one foreign-tag leftover, `_stale_bytecode` -> 1, and the
# notice fires on every red run for as long as the file is on disk. So a header whose first four
# bytes are not this interpreter's magic takes the same skip path as a hash-based one.
_PYC_HEADER = 12
_PYC_MAGIC = slice(0, 4)
_PYC_FLAGS = slice(4, 8)
_PYC_TIMESTAMP = slice(8, 12)
_PYC_HASH_BASED = 0b1
# CPython's own mask on the source mtime before it writes the header (`importlib._bootstrap_
# external._code_to_timestamp_pyc`). Without it a source mtime past 2106 -- or a clock skewed
# there -- compares a 33-bit number against the 32 bits the header can hold and mismatches
# forever.
_PYC_MTIME_MASK = 0xFFFFFFFF

LEAD = "Before calling this red a flake, pre-existing, or caused by the branch:"
DIRTY = (
    "{count} uncommitted change(s) in the tree -- this run measured a tree nobody is merging. "
    "A stashed-baseline A/B cannot see this: both halves run in it."
)
STALE = (
    "{count} .pyc file(s) whose recorded source mtime no longer matches their source, under "
    "the configured code roots -- the "
    "interpreter may be importing a build that predates a fix on disk, which fails "
    "DETERMINISTICALLY in the shape of the defect the test pins. Delete the `__pycache__` "
    "directories under those roots, then re-run before attributing anything."
)


class Hygiene(NamedTuple):
    dirty: int | None  # uncommitted changes; None when git could not answer
    stale: int  # .pyc files whose recorded source mtime no longer matches the source
    roots: int  # how many code roots were scanned


def _segment_runs_pytest(segment: list[str]) -> bool:
    """True when THIS segment actually invokes pytest -- as its own program, or as a module the
    interpreter loads (`-m pytest`, adjacent or fused as `-mpytest`) -- never a substring test
    against text that merely names it.

    Requiring the `-m` shape's argv0 to itself look like a Python interpreter (`python`,
    `python3`, `python3.13`, ...) is cheap insurance: "pytest" is a short enough word that an
    unrelated program taking it as some other flag's value is not implausible.
    """
    command = bashscan.command_words(segment)
    if not command:
        return False
    argv0 = Path(command[0]).name
    if argv0 == PYTEST:
        return True
    if not argv0.startswith(_PYTHON_ARGV0_PREFIX):
        return False
    if f"-m{PYTEST}" in command:
        return True
    # `pairwise`, not the source's `zip(command, command[1:])`: identical semantics, and ruff's
    # RUF007 refuses the `zip` form on this tree.
    return any(current == "-m" and following == PYTEST for current, following in pairwise(command))


def is_pytest_run(command: str) -> bool:
    """True when some segment of `command` actually invokes pytest.

    An unparseable command (`bashscan.tokenize` returns `None`) falls back to the substring
    test rather than going silent: missing a REAL failed pytest run is the worse direction for
    a warn-only note whose whole job is to prevent exactly that misattribution.
    """
    tokens = bashscan.tokenize(command)
    if tokens is None:
        return PYTEST in command
    return any(_segment_runs_pytest(segment) for segment in bashscan.segments(tokens))


def red_exit(raw: Mapping[str, Any]) -> int | None:
    """The non-zero exit code this payload reports, in either shape, or `None`.

    `isinstance(code, bool)` is excluded on purpose: `True` is an `int` equal to 1 in Python,
    so a harness that put a boolean in `exit_code` would otherwise be read as "exited 1".
    """
    response = raw.get("tool_response")
    if isinstance(response, dict):
        code = response.get("exit_code")
        if isinstance(code, int) and not isinstance(code, bool) and code != 0:
            return code
    error = raw.get("error")
    if isinstance(error, str):
        match = _EXIT_CODE_ERROR.match(error)
        if match and int(match.group(1)) != 0:
            return int(match.group(1))
    return None


def _dirty_count(root: Path) -> int | None:
    """Uncommitted changes, or `None` when git could not answer. Never `0` for the latter:
    the two mean opposite things to a person deciding whether to trust a red run."""
    try:
        # S603/S607: list form, never `shell=True`, so nothing is re-parsed by a shell. `root`
        # is the project root the dispatcher resolved or `--root` resolved, not a repository
        # value, and `--` closes the argument list so no pathspec can be smuggled in. `git` is
        # resolved through `PATH` for the reason `gitenv` gives: the machine owner's `git` is
        # the one that must answer.
        completed = subprocess.run(  # noqa: S603 - see the comment above
            ["git", "-C", str(root), "status", "--porcelain", "--"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=STATUS_TIMEOUT_SECONDS,
            env=scrubbed_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return sum(1 for line in completed.stdout.splitlines() if line.strip())


def _recorded_source_mtime(pyc: Path) -> int | None:
    """The source mtime CPython recorded in `pyc`'s header, or `None` when there is not one.

    Four things produce `None` and they all mean the same thing to the caller -- skip this
    file: the header could not be read, it is short, it was written by another interpreter and
    this one will never open it (see `_PYC_MAGIC` above), or it is hash-based and therefore
    carries a hash fragment where an mtime would be (see `_PYC_HASH_BASED` above).
    """
    try:
        with pyc.open("rb") as handle:
            header = handle.read(_PYC_HEADER)
    except OSError:
        return None
    if len(header) < _PYC_HEADER:
        return None
    if header[_PYC_MAGIC] != importlib.util.MAGIC_NUMBER:
        return None
    if int(struct.unpack("<I", header[_PYC_FLAGS])[0]) & _PYC_HASH_BASED:
        return None
    return int(struct.unpack("<I", header[_PYC_TIMESTAMP])[0])


def _stale_bytecode(roots: Iterable[Path]) -> int:
    stale = 0
    for directory in roots:
        for pyc in directory.rglob("*.pyc"):
            if pyc.parent.name != "__pycache__":
                continue
            source = pyc.parent.parent / (pyc.name.split(".")[0] + ".py")
            try:
                if not source.is_file():
                    continue
                recorded = _recorded_source_mtime(pyc)
                if recorded is None:
                    continue
                if recorded != int(source.stat().st_mtime) & _PYC_MTIME_MASK:
                    stale += 1
            except OSError:
                continue
    return stale


def inspect(root: Path, config: Config) -> Hygiene:
    roots = contained_roots(root, config)
    return Hygiene(_dirty_count(root), _stale_bytecode(roots), len(roots))


def notice(found: Hygiene) -> str | None:
    """The fixed sentences for whichever faults are present, or `None` for silence."""
    notes: list[str] = []
    if found.dirty:
        notes.append(DIRTY.format(count=found.dirty))
    if found.stale:
        notes.append(STALE.format(count=found.stale))
    if not notes:
        return None
    return LEAD + "\n- " + "\n- ".join(notes)


def context_for(command: str, root: Path, config: Config) -> str | None:
    if not is_pytest_run(command):
        return None
    return notice(inspect(root, config))
