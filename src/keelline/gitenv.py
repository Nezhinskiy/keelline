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
"""

from __future__ import annotations

import os

# Everything else is dropped, `GIT_DIR` and `GIT_WORK_TREE` above all.
GIT_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT")

# Wall-clock bound on one `git` call (D7: a cap, not read from `config.budgets` or
# `config.native_caps` — no shipped file needs to change with it). Every call either caller makes
# is a local, argument-free, read-only query (`rev-parse`, `remote get-url`, `--version`) against
# the environment below, so it never touches the network; this only guards against a `git` binary
# that hangs outright, and is generous for that without leaving a hook blocked for long.
GIT_TIMEOUT_SECONDS = 5


def scrubbed_env() -> dict[str, str]:
    return {key: os.environ[key] for key in GIT_ENV_KEEP if key in os.environ}
