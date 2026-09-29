`stayfixed detach` no longer un-hides the files of another checkout that is still attached. The
exclude block `attach` writes is shared by every worktree of the repository, so when another
checkout still holds an attach ledger, `detach` now keeps the block, says so on its line, and
reports `exclude_block_kept` in `--json`; the detach of the last attached checkout removes it.
Before, detaching the main checkout showed a still-attached worktree's
`.claude/settings.local.json` and `.codex/rules/` copies in its `git status`.
