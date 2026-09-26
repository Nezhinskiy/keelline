The branch a rendered CI workflow gates — `[ci] gate_branch`, `keelline init --yes
--base-branch`, or the base branch `init` detects from `origin/HEAD` — follows git's own
branch-name rules: a name with `..` or `//`, a component starting with `.` or ending in `.lock`,
a trailing `/` or `.`, or the name `HEAD` is refused, since no repository can have that branch.
`release/2.0` is still a branch name.
