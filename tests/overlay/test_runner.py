"""What the one seam out of this process gives the commands it launches.

Every case here runs `sh` or a nonexistent name and never `gh`, `git` or `pre-commit`: the
subject is the environment, the stdin and the exit-code mapping, not any of those binaries.
"""

from __future__ import annotations

import os
import pty
from pathlib import Path

from keelline.overlay.runner import (
    _ENV_DROP,
    _ENV_FORCE,
    NOT_FOUND,
    TIMED_OUT,
    _SubprocessRunner,
)

PROBE = [
    "sh",
    "-c",
    'echo "tty=$( [ -t 0 ] && echo yes || echo no ) '
    'prompt=${GIT_TERMINAL_PROMPT-unset} dir=${GIT_DIR-unset} index=${GIT_INDEX_FILE-unset}"',
]


def test_a_launched_command_gets_no_stdin_and_no_credential_prompt(tmp_path: Path) -> None:
    # Every call here runs with output captured, so a `git` or `gh` that asks for a credential
    # on an inherited stdin is invisible and blocks for the whole of NETWORK_TIMEOUT_SECONDS.
    # `doctor`'s `ci-ref` row is what makes it a finding rather than an annoyance: the URL it
    # resolves is repository-authored, and a read-only diagnostic must not be holdable by one.
    #
    # The pty is the point of the case: without it this process's own stdin is already not a
    # terminal under pytest, and the assertion would pass with the guard deleted.
    master, slave = pty.openpty()
    saved = os.dup(0)
    try:
        os.dup2(slave, 0)
        done = _SubprocessRunner().run(PROBE, tmp_path)
    finally:
        os.dup2(saved, 0)
        for descriptor in (master, slave, saved):
            os.close(descriptor)
    assert "tty=no" in done.stdout
    assert "prompt=0" in done.stdout


def test_the_variables_that_redirect_git_are_dropped(tmp_path: Path) -> None:
    # A clone into a fresh directory must not inherit what points git at a different repository,
    # index or object store. `GIT_DIR` and `GIT_WORK_TREE` were the only two dropped, and the
    # comment beside them claimed they were "the two" that do it; `GIT_INDEX_FILE` is one of
    # several counterexamples, and is the arm asserted here.
    for name in ("GIT_DIR", "GIT_INDEX_FILE"):
        os.environ[name] = str(tmp_path / name)
    try:
        done = _SubprocessRunner().run(PROBE, tmp_path)
    finally:
        for name in ("GIT_DIR", "GIT_INDEX_FILE"):
            del os.environ[name]
    assert "dir=unset" in done.stdout
    assert "index=unset" in done.stdout
    assert set(_ENV_DROP) >= {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"}
    assert _ENV_FORCE["GIT_TERMINAL_PROMPT"] == "0"


def test_a_command_that_hangs_is_not_reported_as_one_that_is_missing(tmp_path: Path) -> None:
    # `TimeoutExpired` is a `SubprocessError`, so a `gh` that hung for the full five minutes
    # arrived as NOT_FOUND — which every caller reads as "gh is not installed". A wrong finding
    # is worse than a slow one, and the two have different remedies.
    import keelline.overlay.runner as runner

    before = runner.NETWORK_TIMEOUT_SECONDS
    runner.NETWORK_TIMEOUT_SECONDS = 1
    try:
        hung = _SubprocessRunner().run(["sh", "-c", "sleep 5"], tmp_path)
    finally:
        runner.NETWORK_TIMEOUT_SECONDS = before
    assert hung.code == TIMED_OUT
    # Non-vacuous: a binary that really is missing still answers NOT_FOUND, which is the mapping
    # the global constraints ask for — an optional binary is a finding, never a traceback.
    assert _SubprocessRunner().run(["keelline-no-such-binary"], tmp_path).code == NOT_FOUND
