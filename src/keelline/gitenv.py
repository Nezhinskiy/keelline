"""The environment every `git` this project runs is given, and the bound on how long it may take.

One module because there are two callers and the rule is the same for both, and being the same
for both is the point. `memory.store._git` scrubbed and said why — "it must be a real git
answer, not one an inherited `GIT_DIR` produced" — while `hooks.dispatch._git_toplevel` passed
no `env=` at all and inherited whatever the session had. That one feeds `project_root()`, which
every hook decision is derived from, so an inherited `GIT_DIR` or `GIT_WORK_TREE` made every
handler in the process answer for a different repository than the one the user is sitting in.

A leaf module: it imports nothing from `keelline`, so the hook path pays no area import to
reach it, and neither caller has to import the other's area to share the constant.

**`PATH` is here on purpose, and it is the one entry with a cost.** `git` is resolved through it
rather than pinned to `/usr/bin/git`, because the machine owner's `git` is the one that must
answer — a hardcoded path is what picks the Xcode shim on macOS over the working `git` they
installed. A committed `.claude/settings.json` `env` block can set `PATH` in a non-interactive
session, which is a harness-level exposure this module cannot close and does not pretend to.

`git_run` is the runner the ledger and docs areas call; `memory.store._git` keeps its
three-valued answer and its usability probe, which are the memory lane's, and is not rewritten
here (Premise 17).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Everything else is dropped, `GIT_DIR` and `GIT_WORK_TREE` above all.
GIT_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT")

# Wall-clock bound on one `git` call (D7: a cap, not read from `config.budgets` or
# `config.native_caps` — no shipped file needs to change with it). It is the bound for a local,
# argument-free, read-only query against the environment below (`rev-parse`, `remote get-url`,
# `--version`), which neither touches the network nor grows with the repository: it guards
# against a `git` binary that hangs outright, and is generous for that without leaving a hook
# blocked for long. A caller whose query is not that shape passes its own wider bound instead
# and says why beside it — `keelline.ledger.write.FETCH_TIMEOUT_SECONDS` for one that reaches
# the network, `keelline.ledger.git.QUERY_TIMEOUT_SECONDS` for one that is merely slow, since a
# `log --all` over a long history is not a five-second `rev-parse`. Tune this number for the
# hang, not for a remote and not for a long history.
GIT_TIMEOUT_SECONDS = 5


def scrubbed_env() -> dict[str, str]:
    return {key: os.environ[key] for key in GIT_ENV_KEEP if key in os.environ}


def git_run(
    root: Path, *args: str, timeout: float = GIT_TIMEOUT_SECONDS, stdin: str | None = None
) -> tuple[int, str]:
    """`(returncode, stdout)` of `git -C root args`; `(-1, "")` when git could not be run.

    The one place this project runs `git` outside the memory store's own resolver: every
    argument list is built from constants by the caller, every pathspec follows `--`, and no
    configuration value reaches this list without `contained()` having refused the
    `-`-shaped ones (§3). Resolved through PATH for the reason above: the machine owner's git
    must answer. A non-zero exit is returned, not collapsed — `check-ignore` answers 1 for
    "nothing matched", and that is an answer.

    **Decoded with `surrogateescape`, both ways.** git speaks bytes, and a worktree path, a
    common directory, a name in `ls-files` or a ref can hold one the locale cannot decode — a
    latin-1 filename on Linux. Strict decoding raised `UnicodeDecodeError`, a `ValueError`
    nothing here caught, out of every caller as an internal error; and it did so for stderr
    too, which nobody reads. Escaped instead, a byte comes back as the same `str` `os.listdir`
    and `sys.argv` give for it, so an answer is compared with, and opens, the path it names,
    and a name read off the disk goes back to git on `stdin` as its own bytes. The answer is
    lossless rather than a placeholder, so every caller still decides about the path that is
    really there, and no refusal becomes a pass by way of the decode. What it does not make
    safe is writing that `str` into a UTF-8 file: a caller whose answer ends up in one checks
    it itself, as `project.detect` does for the base branch.

    A `stdin` with no bytes at all under the locale — a character a non-UTF-8 locale cannot
    spell — is `(-1, "")`: git could not be asked, which is what that answer already says.
    """
    try:
        completed = subprocess.run(  # noqa: S603 - see the docstring
            ["git", "-C", str(root), *args],  # noqa: S607 - PATH on purpose, see the module docstring
            input=stdin,
            capture_output=True,
            text=True,
            errors="surrogateescape",
            check=False,
            timeout=timeout,
            env=scrubbed_env(),
        )
    except (OSError, subprocess.SubprocessError, UnicodeEncodeError):
        return -1, ""
    return completed.returncode, completed.stdout
