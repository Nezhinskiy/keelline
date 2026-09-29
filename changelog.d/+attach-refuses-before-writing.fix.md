`stayfixed attach` now refuses two cases by name before it writes anything. A repository whose
`memory.mode` is not `overlay` used to be refused only after `.gitignore`, `.codex/rules/`,
`.claude/settings.local.json`, the ledger and the overlay's record of the project had been
written, and `stayfixed attach --check` exited `0` for it; both now exit `2`. A `.stayfixed`,
`.codex` or `.claude` that is a symlink used to have `.gitignore` and more written and then stop
with `internal error: UnsafePath`; it is now refused, naming the symlink. When the harness memory
link is held back until the store is approved, `attach` now says so and names the way out: run
`stayfixed memory trust --in-repo-memory`, then `stayfixed attach` again.
