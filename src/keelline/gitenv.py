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
import sys
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

# What `git_run`'s `(-1, "")` means, in one clause a caller's message can build on. The runner
# does not say which of the three it was, because none of them is an answer about the
# repository: a caller that words `-1` as one cause — "git is not installed", "the fetch timed
# out" — is wrong about the other two. What git printed is never one of them: its output is
# decoded losslessly, so an answer is always read.
NO_ANSWER = "git could not be run, ran past its time limit, or could not be given its input"


def in_work_tree(root: Path) -> bool:
    """Whether `root` or a directory above it holds a `.git` entry, which is how git itself finds
    the repository: a directory in a clone, a file in a worktree or a submodule.

    Read off the disk and never asked of git, because git refuses that question the same way it
    refused the one before it: a `rev-parse` that times out, or that exits 128 on a checkout it
    judges of dubious ownership (`safe.directory`) or on a worktree whose gitdir is gone, reads as
    "no repository" — and a guard that took that answer let its caller through. `GIT_DIR` is
    scrubbed from every `git` this project runs, so the `.git` entry is the one git would use.
    """
    return any(os.path.lexists(directory / ".git") for directory in (root, *root.parents))


def scrubbed_env() -> dict[str, str]:
    return {key: os.environ[key] for key in GIT_ENV_KEEP if key in os.environ}


def pipe_encoding() -> str:
    """The codec `git_run` decodes git's output and encodes its `stdin` with: the filesystem's,
    the one `os.fsdecode`, `Path.iterdir` and `sys.argv` use for the same names.

    Not the locale's. The two agree on Linux, where the filesystem codec follows the locale, and
    differ on macOS, where it is UTF-8 whatever `LC_ALL` says: under a latin-1 locale there, git's
    `café.md` came back as mojibake and a name sent on `stdin` reached git as bytes that were not
    its own, so every comparison between git's answer and a path missed — a gitignored document
    read as not ignored. The error handler is `surrogateescape`, the filesystem's own on POSIX.

    Named once so `answer_bytes` undoes exactly what `git_run` did: where the codec is latin-1
    every byte decodes, so an answer carries no surrogate escape to show it was not UTF-8, and
    only re-encoding it with the same codec recovers the bytes git printed.
    """
    return sys.getfilesystemencoding()


def answer_bytes(answer: str) -> bytes:
    """The bytes git printed for a `git_run` answer, for a caller that must read them as UTF-8
    whatever the locale: decoding is lossless both ways, so this is exact, except that text
    mode has already turned each `\\r\\n` and lone `\\r` into `\\n`.
    """
    return answer.encode(pipe_encoding(), "surrogateescape")


def git_run(
    root: Path, *args: str, timeout: float = GIT_TIMEOUT_SECONDS, stdin: str | None = None
) -> tuple[int, str]:
    """`(returncode, stdout)` of `git -C root args`; `(-1, "")` when git gave no answer.

    The one place this project runs `git` outside the memory store's own resolver: every
    argument list is built from constants by the caller, every pathspec follows `--` or
    `--end-of-options`, and no configuration value reaches this list without `contained()`
    having refused the `-`-shaped ones. Resolved through PATH for the reason above: the machine
    owner's git must answer. A non-zero exit is returned, not collapsed — `check-ignore` answers
    1 for "nothing matched", and that is an answer.

    **Decoded with `surrogateescape`, both ways.** git speaks bytes, and a worktree path, a
    common directory, a name in `ls-files` or a ref can hold one the filesystem's codec cannot
    decode — a latin-1 filename on Linux. Strict decoding raised `UnicodeDecodeError` out of
    every caller as an internal error, and it did so for stderr too, which nobody reads; reading
    such output as no answer instead threw a real answer away, and a caller that took "no
    answer" for "nothing" then passed what it should have refused. Escaped, and in the
    filesystem's codec (`pipe_encoding`), a byte comes back as the same `str` `os.listdir` and
    `sys.argv` give for it, so an answer is compared with, and opens, the path it names, and a
    name read off the disk goes back to git on `stdin` as its own bytes. The answer is lossless
    rather than a placeholder, so every caller still decides about the path that is really
    there. What it does not make safe is writing that `str` into a UTF-8
    file or parsing it as UTF-8 text: a caller whose answer ends up in one checks it itself, as
    `assess.rule.read_base` does for the base's `keelline.toml`.

    No answer is three things, and `NO_ANSWER` names all three: git could not be launched, it
    ran past `timeout`, or `stdin` held a character the filesystem's codec has no bytes for: a
    name from a note or a file written in UTF-8, asked on Linux under a locale that is not. A
    name read off the disk never does, because it was decoded with that same codec.
    """
    try:
        completed = subprocess.run(  # noqa: S603 - see the docstring
            ["git", "-C", str(root), *args],  # noqa: S607 - PATH on purpose, see the module docstring
            input=stdin,
            capture_output=True,
            encoding=pipe_encoding(),
            errors="surrogateescape",
            check=False,
            timeout=timeout,
            env=scrubbed_env(),
        )
    except (OSError, subprocess.SubprocessError, UnicodeEncodeError):
        return -1, ""
    return completed.returncode, completed.stdout
