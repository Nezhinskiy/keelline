`stayfixed attach` no longer leaves its machine-local files for `git status` to list: the note
link tree, the `.codex/rules/` copies and, when `attach` writes it, `.claude/settings.local.json`
are hidden through a marked block in the repository's own exclude file (`.git/info/exclude`,
shared by every worktree), listing only the paths git does not already ignore. `.gitignore` is
written only when it does not already hide `.stayfixed/local/` and `.stayfixed/assessment.json`,
so a checkout that hides everything itself is not touched. `stayfixed detach` removes the block,
the empty `paths.memory` directory and the empty directory above it that `attach` created, and
the empty `~/.claude/projects/<slug>/` directory the harness memory link sat in.
