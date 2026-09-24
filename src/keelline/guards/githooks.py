"""The chained `prepare-commit-msg` hook and its per-repository installer.

The hook is a Keelline artifact recognised by its marker line, `HOOK_MARKER`.

Installed into `git rev-parse --git-path hooks`, never through `core.hooksPath`: a global
setting is overridden by any repository that sets its own and silently competes with husky
elsewhere on the machine, while `--git-path` honours a `core.hooksPath` the repository already
has — computing `<common-dir>/hooks` by hand would install into a directory git never reads
when one is set. Hooks resolve from the common directory, so one installation covers the main
checkout and every worktree.

A foreign hook of the same name is kept as `<name>.local` and the shipped hook `exec`s it
last, so nothing that was already running stops running. `uninstall` puts it back.

This is the one place this lane writes outside a project root on purpose: the hooks
directory is git's, and in a worktree it is not under the checkout at all. The writes are
`fsops.write_atomically` on the hook path and a rename of the foreign hook beside it; both are
enumerated writes, as every write Keelline makes is.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import NamedTuple

from keelline import fsops
from keelline.errors import Refusal
from keelline.gitenv import GIT_TIMEOUT_SECONDS, scrubbed_env

HOOK_NAME = "prepare-commit-msg"
HOOK_MARKER = "# keelline:prepare-commit-msg"
LOCAL_SUFFIX = ".local"
# The mode the hook is given. Not a config key and not a bound on anything: git runs a hook
# only if it is executable, so any other value is a hook that silently never runs. Owner and
# group write are off for the same reason `fsops` picks conservative modes.
_EXECUTABLE = 0o755

_CHAIN_LINE = '    exec "$previous" "$@"'
# Every line of the hook stays under ruff's line length: the formatter never reflows a string
# literal, and a lint-suppression comment inside one would ship as hook text, so the long
# messages are shell variables. `{}` are absent from the shell on purpose; the only braces are
# the f-string's, which is why the command is chosen into a plain variable rather than into a
# shell function.
HOOK_TEXT = f"""#!/usr/bin/env bash
{HOOK_MARKER}
# Strip AI/tool attribution trailers before the commit message is presented.
#
# prepare-commit-msg rather than commit-msg on purpose: `git commit --no-verify` bypasses
# pre-commit and commit-msg, but not this hook. It is still only the local convenience layer;
# the authoritative gate is `keelline commit check` in CI, which sees commits this machine
# never produced. Written, and removed again, by keelline's git-hook installer; no `keelline`
# subcommand offers it yet, so today it is reached from Python as `guards.api.install(root)`.
#
# Chains to whatever hook was here before, kept beside this one as `<hook>.local`, so
# installing this never silently disables husky, pre-commit, or what the repository had.
set -euo pipefail

msg_file="$1"
gate="CI's commit check is the gate"
failed="keelline: commit strip failed; $gate"
absent="keelline: not installed for this shell; trailers are not stripped locally; $gate"
quiet='^nothing to strip'

# Expanded unquoted where it is used, so the two-word form splits into words. It is only ever
# one of the two literals assigned just below, and never anything a repository chose.
runner=""
if command -v keelline >/dev/null 2>&1; then
    runner="keelline"
elif python3 -c 'import keelline' >/dev/null 2>&1; then
    runner="python3 -m keelline"
fi

# `commit strip` prints one line on stdout: "stripped N ..." or "nothing to strip". Only a
# rewrite is worth a line on the terminal, so the quiet one is filtered out and everything
# else is said. The branch is on the command's own status and never on `grep`'s: `grep -v`
# exits 1 when it selects no lines, which is exactly the quiet case, so a `||` hung off the
# pipe announces a failure on every clean commit. No outcome here may fail the commit.
if [ -z "$runner" ]; then
    printf '%s\\n' "$absent" >&2
elif out=$($runner commit strip "$msg_file"); then
    printf '%s\\n' "$out" | grep -v "$quiet" >&2 || true
else
    printf '%s\\n' "$failed" >&2
fi

previous="$0.local"
if [ -x "$previous" ]; then
{_CHAIN_LINE}
fi
"""


class Installed(NamedTuple):
    path: Path
    preserved: Path | None
    replaced: bool


class Removed(NamedTuple):
    path: Path
    restored: Path | None


def hooks_dir(root: Path) -> Path:
    try:
        # S603/S607: list form; `root` is a path this process was handed by a person or a
        # test, not a repository value; `git` through PATH because the owner's git answers.
        # No `--` after `--git-path hooks`: measured, git prints a literal `--` as a second
        # line there. `hooks` is a constant, so nothing here is a value to close off.
        completed = subprocess.run(  # noqa: S603
            ["git", "-C", str(root), "rev-parse", "--git-path", "hooks"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env=scrubbed_env(),
        )
    # Neither refusal carries a byte this module did not compute, for the reason `commit.commits_in`
    # states beside its own three: `rev-parse`'s stderr is repository-authored — it quotes the
    # offending CONFIG VALUE, `core.hooksPath` included — and `TimeoutExpired.__str__` renders the
    # whole argv. `root` is the caller's own path and is the actionable part; it is all that is
    # printed. This defect was found and fixed in `commits_in` during this lane's own review and
    # was still here, which is why the reasoning is repeated rather than pointed at.
    except (OSError, subprocess.TimeoutExpired):
        raise Refusal(f"git could not name the hooks directory of {root}") from None
    answer = completed.stdout.strip()
    if completed.returncode != 0 or not answer:
        raise Refusal(
            f"git could not name the hooks directory of {root}; run it yourself to see why"
        )
    path = Path(answer)
    return path if path.is_absolute() else root / path


def _ours(path: Path) -> bool:
    try:
        return HOOK_MARKER in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def install(root: Path) -> Installed:
    directory = hooks_dir(root)
    target = directory / HOOK_NAME
    local = directory / (HOOK_NAME + LOCAL_SUFFIX)
    if target.is_symlink():
        raise Refusal(f"{target} is a symlink; refusing to write through it")
    if target.is_dir():
        raise Refusal(f"{target} is a directory; refusing to install a hook over it")
    replaced = target.exists() and _ours(target)
    # A `.local` found where our hook is *not* installed was put there by somebody else, and
    # the shipped hook `exec`s whatever sits at that name, so installing over it would run a
    # stranger's file under Keelline's name. Note the bound, which is the whole of the
    # contract: this fires only while our hook is absent. Once ours is installed, the `.local`
    # beside it is presumed to be the one we preserved, and a file that appears there
    # afterwards is vouched for by nothing here — see `uninstall`.
    if local.exists() and not replaced:
        raise Refusal(f"{local} already exists and was not preserved by keelline; move it aside")
    preserved: Path | None = None
    if target.exists() and not replaced:
        target.rename(local)  # beside the hook, in git's own directory: an enumerated write
        # Its mode is kept as found: `chmod -x` is how a developer switches a hook off, and
        # the chain tests `-x` for exactly that reason.
        preserved = local
    fsops.write_atomically(target, HOOK_TEXT)
    os.chmod(target, _EXECUTABLE)  # a git hook must be executable to run at all
    return Installed(target, preserved, replaced)


def uninstall(root: Path) -> Removed:
    directory = hooks_dir(root)
    target = directory / HOOK_NAME
    local = directory / (HOOK_NAME + LOCAL_SUFFIX)
    if not target.exists() or target.is_symlink() or not _ours(target):
        return Removed(target, None)
    target.unlink()
    # Whatever sits at `.local` is restored, and this does *not* check that install put it
    # there. It cannot: `install` refuses a stray `.local` only while our hook is absent, so a
    # file dropped beside an installed hook is unexamined — and the installed hook has been
    # `exec`ing it on every commit since, which is the larger fact. Restoring it is therefore
    # the honest end of that state rather than a new exposure, and it is deliberate: the
    # `.local` name is the plan's contract with the `setup` lane, and a provenance marker or an
    # unconditional refusal here would be this module inventing a different one.
    if local.exists():
        local.rename(target)
        return Removed(target, target)
    return Removed(target, None)
