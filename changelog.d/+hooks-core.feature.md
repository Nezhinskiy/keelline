Keelline's hooks now fire in a real session. The plugin ships `hooks/hooks.json`, which both
Claude Code and Codex read with no configuration, and a shell wrapper that finds a Python 3.11 or
newer, runs from your project root, and refuses with a named reason rather than letting a broken
guard read as permission. The dispatcher also remembers what it has already said, so a
once-per-session notice arrives once instead of on every tool call.

The wrapper treats its environment the way the rest of Keelline treats a repository: a variable
may say *where* something goes, never *which program runs*. A committed `.claude/settings.json`
`env` block applies without a trust prompt, so the interpreter list `KEELLINE_PYTHON_CANDIDATES`
names is honoured only from an interactive terminal; no `python3` whose resolved path lies inside
**any checkout** of the repository is ever run, whatever `PATH` spelling reached it — a linked
worktree is the same repository, and a clone ships its tree into every checkout; the `git` that
answers for the project root is taken from a fixed list of absolute paths with an allowlisted
environment, never from `PATH`; and a relative `CLAUDE_PLUGIN_DATA` gets no diagnostics sink at
all rather than one anchored inside the checkout. If your only Python 3.11 lives inside your
checkout you will see `KL_NO_PY` and a red `wrapper` row in `keelline doctor`, with the remedy,
instead of a hook that silently runs your tree's own program. Every fault the wrapper can see
before Keelline runs — no policy argument, no `git`, no interpreter, a launcher it cannot read, a
project root it cannot enter — prints its own token.
