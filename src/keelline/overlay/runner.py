"""The one seam between this area and the outside world.

Everything `overlay` does that leaves this process — asking GitHub for a repository, cloning
one, installing a commit hook — goes through `Runner.run`, so a test asserts *the argv it would
have run* against a stub instead of shelling out to `gh`, `git` or `pre-commit`. Mocking
`subprocess.run` would hide the argv, which is the only part of these calls that can be wrong in
a way a user notices: a missing `--private` publishes somebody's private overlay.

A missing binary is a finding, never a traceback (the global constraints make `gh`, `git` and
`pre-commit` optional), so an `OSError` from the launch becomes `Completed(NOT_FOUND, ...)` and
the caller turns it into a note.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# The shell's own code for "command not found", used here for a binary that could not be
# launched at all, so a caller has one number to read rather than an exception to catch.
NOT_FOUND = 127
# Wall-clock bound on one call, and deliberately far wider than `gitenv.GIT_TIMEOUT_SECONDS`
# (D7: a cap, not a config key). That one bounds a local, argument-free query that neither
# touches the network nor grows with the repository; every call here does the opposite — `gh
# repo create --clone` waits on GitHub to generate a repository from a template, and the clone
# that follows comes down the wire. Tune this for a hung process, not for a slow link.
NETWORK_TIMEOUT_SECONDS = 300
# Inherit the environment rather than scrub it: these are the machine owner's own authenticated
# commands, and `gh` needs its token and `git` its ssh-agent to work at all. The two variables
# that are dropped are the two that point git at a *different* repository than the directory it
# was given, which is exactly what a clone into a fresh directory must not inherit.
_ENV_DROP = ("GIT_DIR", "GIT_WORK_TREE")


@dataclass(frozen=True)
class Completed:
    code: int
    stdout: str
    stderr: str


class Runner(Protocol):
    def run(self, argv: list[str], cwd: Path) -> Completed: ...


class _SubprocessRunner:
    def run(self, argv: list[str], cwd: Path) -> Completed:
        env = {key: value for key, value in os.environ.items() if key not in _ENV_DROP}
        try:
            done = subprocess.run(  # noqa: S603 - list form, never a shell; see the module docstring
                # Resolved through PATH on purpose: the owner's own `gh` and `git` must answer.
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
                timeout=NETWORK_TIMEOUT_SECONDS,
                env=env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return Completed(NOT_FOUND, "", f"{argv[0]} could not be run: {exc}")
        return Completed(done.returncode, done.stdout, done.stderr)


def subprocess_runner() -> Runner:
    """The real one. List form, never `shell=True`, and every repository- or argument-derived
    value passed after a `--` so a name shaped like an option cannot become one (§3)."""
    return _SubprocessRunner()
