`stayfixed attach` no longer leaves its machine-local files for `git status` to list. The note
link tree, the `.codex/rules/` copies and, when `attach` writes it, `.claude/settings.local.json`
are hidden through a marked block in the repository's own exclude file (`.git/info/exclude`,
which every worktree shares). A path your own exclude file or global excludes file already hides
gets no line; a committed `.gitignore` does not count, because a pull can change it. `.gitignore`
is now written only when it does not already hide `.stayfixed/local/` and
`.stayfixed/assessment.json`. `stayfixed detach` removes the block and gives the exclude file back
as it was, but keeps the block while another checkout of the repository is still attached
(`exclude_block_kept` in `--json`). It also removes the empty directories `attach` created, which
it used to leave behind: `paths.memory`, the one above it and the harness's
`~/.claude/projects/<slug>/`.
