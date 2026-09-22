"""The one seam between Keelline and the programs it launches.

Everything the areas that launch a program (`overlay`, `attach`, `doctor`, `setup`, and the
release commands) do that leaves this process — asking GitHub for a repository, cloning
one, installing a commit hook — goes through `Runner.run`, so a test asserts *the argv it would
have run* against a stub instead of shelling out to `gh`, `git` or `pre-commit`. Mocking
`subprocess.run` would hide the argv, which is the only part of these calls that can be wrong in
a way a user notices: a missing `--private` publishes somebody's private overlay.

A missing binary is a finding, never a traceback (the global constraints make `gh`, `git` and
`pre-commit` optional), so an `OSError` from the launch becomes `Completed(NOT_FOUND, ...)` and
the caller turns it into a note. A binary that ran and never returned gets its own code,
`TIMED_OUT`, because "not installed" and "hung for five minutes" are different findings.
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
# `timeout(1)`'s own code, and a separate one on purpose. `TimeoutExpired` is a
# `SubprocessError`, so a `gh` that hung for the full `NETWORK_TIMEOUT_SECONDS` used to arrive
# as `NOT_FOUND` -- which every caller reads as "gh is not installed". A wrong finding is worse
# than a slow one, and the two states have different remedies.
TIMED_OUT = 124
# Wall-clock bound on one call, and deliberately far wider than `gitenv.GIT_TIMEOUT_SECONDS`
# (D7: a cap, not a config key). That one bounds a local, argument-free query that neither
# touches the network nor grows with the repository; every call here does the opposite — `gh
# repo create --clone` waits on GitHub to generate a repository from a template, and the clone
# that follows comes down the wire. Tune this for a hung process, not for a slow link.
NETWORK_TIMEOUT_SECONDS = 300
# Inherit the environment rather than scrub it: these are the machine owner's own authenticated
# commands, and `gh` needs its token and `git` its ssh-agent to work at all. What is dropped is
# what points git at a *different* repository, or a different index or object store, than the
# directory it was given -- which is exactly what a clone into a fresh directory must not
# inherit. `gitenv.scrubbed_env()` reaches the same end from the other side, with a five-key
# allowlist; this seam cannot, because the owner's own authentication is the point of it.
#
# **This list is a trade-off and is not exhaustive, and the comment that said it was the two
# that redirect git was wrong.** `GH_HOST` and `GH_CONFIG_DIR` redirect `gh` the same way and
# are kept deliberately: they are how a GitHub Enterprise owner reaches their own host, and
# dropping them would break that installation outright to close a gap the inherited token does
# not have. A lane that needs them gone should say which call and why.
_ENV_DROP = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
)
# Forced rather than inherited, and the reason the cap above means anything. `git` and `gh` ask
# for a credential on stdin, and every call here runs with output captured -- so a prompt is
# invisible and blocks for the whole of `NETWORK_TIMEOUT_SECONDS`, which a caller cannot tell
# from a hang. What makes that a finding rather than an annoyance is which callers reach the
# network through here: `overlay create --template` launches `gh repo create` and a clone, whose
# authentication is the machine owner's and which prompts when it is missing, and
# `release.pins.released` runs `git ls-remote` against the public repository for `keelline init`
# and for `doctor`'s `ci-ref` row -- a write meant to run non-interactively and a read-only
# diagnostic, neither of them something a person is sitting in front of waiting to type a
# password.
#
# **This used to say the `ci-ref` row resolves a repository-authored URL, and it does not.** That
# row has asked about `keelline.REPOSITORY_URL`, a module constant, since the wave-4 lane that
# gave it one. The control is unchanged and still needed; what was wrong was the sentence
# explaining it, which named the one caller it had stopped applying to -- and a false rationale on
# a hardening is how a later lane concludes the hardening is unnecessary.
_ENV_FORCE = {"GIT_TERMINAL_PROMPT": "0"}


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
        env.update(_ENV_FORCE)
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
                # Closed, not inherited. See `_ENV_FORCE`: a prompt on an inherited stdin is
                # invisible behind `capture_output` and outlasts nothing.
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return Completed(
                TIMED_OUT, "", f"{argv[0]} did not finish within {NETWORK_TIMEOUT_SECONDS}s"
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return Completed(NOT_FOUND, "", f"{argv[0]} could not be run: {exc}")
        return Completed(done.returncode, done.stdout, done.stderr)


def subprocess_runner() -> Runner:
    """The real one. List form, never `shell=True`, and every repository- or argument-derived
    value passed after a `--` so a name shaped like an option cannot become one (§3)."""
    return _SubprocessRunner()
