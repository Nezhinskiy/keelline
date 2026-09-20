"""The one `git` the suite runs against a fixture repository, and the environment it runs in.

Twenty-three test modules each defined their own, and the copies had drifted apart in five
ways at once: thirteen inherited `os.environ` whole, seven pinned `HOME` under `tmp_path` and
thirteen left the developer's real one, five forced a committer identity and fifteen took
whatever the machine had, four never set `GIT_TERMINAL_PROMPT`, and twelve lines across four
modules had drifted from `os.devnull` to the literal `"/dev/null"`. Nothing held them to each
other, so each fixture was protected by whichever subset its author happened to write.

Here rather than in each module because there is no reason left for the copies: the sentence
that used to justify them — "`tests/` is not a package (CONTRIBUTING…)" — was false and was
deleted in the wave that follows this one's, `tests/__init__.py` is tracked, and
`tests/snapshot.py` is the precedent for a shared test module.

**The environment is sealed rather than inherited, and that is the hardening.** An inherited
`GIT_DIR`, `GIT_WORK_TREE` or `GIT_INDEX_FILE` points `git` at a repository other than the one
it was given — which is the defect `keelline.gitenv` and `keelline.runner` both exist to close,
and it is worse here than in production: these calls are `init`, `add` and `commit`, so a
redirected fixture does not read the wrong repository, it *writes* to it. `GIT_CONFIG_GLOBAL`
and `GIT_CONFIG_SYSTEM` go to `os.devnull` for the reason `tests/memory/test_store.py` gave in
prose: `commit.gpgsign`, `core.hooksPath` and `init.templateDir` can each hang or fail a commit
that has nothing to do with the code under test.

**`PATH` is passed through rather than pinned**, for the reason `keelline.gitenv`'s module
docstring gives about production: the machine owner's own `git` is the one that must answer,
and a hardcoded `/usr/bin:/bin` is what picks the Xcode shim on macOS over the `git` they
installed. Two modules pinned it; that was a narrowing nothing needed, and this widens it.

**The committer identity is forced**, so a machine whose `user.email` is only in the global
configuration this module has just pointed at `os.devnull` can still commit, and so that two
runs of the same fixture on two machines produce the same author. Three modules were passing
`-c user.email=…` at the call site to buy exactly this; those call sites still work and are
now merely redundant.

`home` defaults to `root.parent`, which is inside `tmp_path` for every fixture in this suite:
the global constraint is that a test never reads or writes the developer's real home, and
pointing the two configuration variables at `os.devnull` is the first half of that, not the
whole of it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

# The one spelling of the skip, published here because five modules had written it out.
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

# What survives from the ambient environment. `PATH` for the reason in the module docstring;
# the rest is what makes `git` able to run and report at all on the three platforms. Everything
# else is dropped, `GIT_DIR` and `GIT_WORK_TREE` above all — the same rule
# `keelline.gitenv.GIT_ENV_KEEP` states for production, with `TMPDIR` added because these
# fixtures are built under one.
ENV_KEEP = ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "TMPDIR")


def env(home: Path, **extra: str) -> dict[str, str]:
    """The sealed environment one fixture `git` runs in, with `extra` layered on top.

    `extra` is for a module whose difference is real: `tests/guards/test_githooks.py` puts a
    `keelline` shim on `PATH` because its `git commit` has to run the commit-msg hook it just
    installed, and that shim is the branch the test exists to exercise.
    """
    sealed = {key: os.environ[key] for key in ENV_KEEP if key in os.environ}
    sealed.update(
        {
            "HOME": str(home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }
    )
    sealed.update(extra)
    return sealed


def run_git(
    root: Path, *args: str, home: Path | None = None, **extra: str
) -> subprocess.CompletedProcess[str]:
    """`git -C root args` in the sealed environment, whatever it exits with.

    For the handful of call sites whose subject *is* the exit code or the streams — a
    `check-ignore` that answers 1 for "no match", a `git commit` expected to be rejected by the
    hook under test, a `config --get` expected to find nothing. `git` below is this with
    `check=True` and only the stdout, which is what every other call site wants.

    `stdin` is closed rather than inherited, which is the second half of what
    `GIT_TERMINAL_PROMPT` buys and the reason `keelline.runner` gives for the same line: every
    call here captures its output, so a credential prompt would be invisible and would block
    until the test run was killed.
    """
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env(home if home is not None else root.parent, **extra),
        stdin=subprocess.DEVNULL,
    )


def git(root: Path, *args: str, home: Path | None = None, **extra: str) -> str:
    """`git -C root args` in the sealed environment; its stdout, raising on a non-zero exit."""
    done = run_git(root, *args, home=home, **extra)
    done.check_returncode()
    return done.stdout
