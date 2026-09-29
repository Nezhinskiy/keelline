`stayfixed attach` now refuses a repository whose `memory.mode` is not `overlay` before it writes
anything, and `stayfixed attach --check` answers the same refusal with the same exit code. It
used to write `.gitignore`, `.codex/rules/`, `.claude/settings.local.json`, its ledger and, in
the overlay, the project's record and note directories before refusing, and `stayfixed doctor`
then reported the repository attached. When the harness memory link is held back until the
store is approved, `attach` now says so and names the way out: run
`stayfixed memory trust --in-repo-memory`, then `stayfixed attach` again.
