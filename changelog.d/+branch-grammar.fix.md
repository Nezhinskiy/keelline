The branch a rendered CI workflow gates — `[ci] gate_branch`, `keelline init --yes
--base-branch`, or the base branch `init` detects from `origin/HEAD` — follows git's own
branch-name rules: a name with `..` or `//`, a component starting with `.` or ending in `.lock`,
a trailing `/` or `.`, or the name `HEAD` is refused, since no repository can have that branch.
`release/2.0` is still a branch name. `[project] base_branch` and `release_branch` follow the same
rules: `keelline.toml` does not load with either outside them, and the refusal names the key, where
`keelline gate` used to blame a `--base` nobody had passed. `plan check` and `test attribute`
compare against `refs/remotes/origin/<base_branch>` by default, spelled in full as `assess`, `gate`
and `adopt promote` spell it, so a tag called `origin/main` no longer stands in for the branch.
