Keelline's hook wrapper and `keelline doctor` now treat an environment variable the same way the
rest of Keelline treats a repository: a variable may say *where* something goes, and never *which
program runs* or *whose bytes are being read*. A committed `.claude/settings.json` `env` block
applies without a trust prompt in a non-interactive session, so a repository could reach all
three of the following, and can no longer reach any of them.

`KEELLINE_PYTHON_CANDIDATES` chose the interpreter `hooks/run-hook.sh` executed on every tool
call, which meant a repository could commit a program and have it run before any Keelline guard.
It is now honoured only when the wrapper's stdin is a terminal — the rule `KEELLINE_CONFIG` and
`XDG_CONFIG_HOME` already follow — so debugging the probe by hand still works and a hook cannot
be redirected. The built-in list's last entry is a `PATH` lookup and `PATH` reaches a hook the
same way, so no candidate whose resolved path lies inside the project root is used either,
whatever spelling reached it. If your interpreter genuinely lives inside your checkout — a
vendored toolchain, or an in-tree virtual environment that is the only `python3` on `PATH` — and
none of the four built-in absolute paths answers on your machine, you will see `KL_NO_PY` and a
red `wrapper` row in `keelline doctor` instead of a hook that silently runs your tree's own
program. The project root is resolved by a `git` with an allowlisted environment, so an
inherited `GIT_DIR` or `GIT_WORK_TREE` can no longer make a hook read a different repository's
configuration, budgets and notes. A launcher that exists and cannot be read now refuses with its
own `KL_NO_LAUNCHER` token instead of an unattributed exit `2`, and a project root that was named
and cannot be entered says `KL_NO_ROOT` instead of silently running in whatever directory the
harness happened to use.

`keelline doctor` no longer executes a plugin root that came from the environment. With a wheel
installation there is no self-derived root, and `CLAUDE_PLUGIN_ROOT` could then point the
`wrapper` check at a `hooks/run-hook.sh` the inspected repository had committed — which was run,
and then reported green. That check now reports `skip` and says why; `files` still reads the
wrapper's executable bit and says whose root it measured.

The `diagnostics` row reports a count and no longer quotes the hook sink's log. The log is found
through `${CLAUDE_PLUGIN_DATA}`, so nothing in `doctor` can establish that Keelline wrote it, and
`keelline doctor --json` is relayed to a model verbatim. The read is bounded by the sink's own
cap as well, which until now was enforced only when writing.

Two smaller repairs in the same family. A `[ci] ref` naming a git transport helper (`ext::…`) is
refused rather than handed to `git ls-remote`, on every version of git. And every command this
project launches — `gh`, `git`, `pre-commit` — now runs with stdin closed and
`GIT_TERMINAL_PROMPT=0`, so a credential prompt cannot hold a read-only diagnostic open for five
minutes, with a distinct exit code for a command that hung rather than one that is not installed.
