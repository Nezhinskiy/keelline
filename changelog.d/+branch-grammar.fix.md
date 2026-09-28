The branch a rendered CI workflow gates — `[ci] gate_branch`, `stayfixed init --yes
--base-branch`, or the base branch `init` detects — is held to one grammar, a strict subset of
git's own branch names: letters, digits, `.`, `_`, `-` and `/`, led by a letter or digit, and
never a name git refuses — `..` or `//`, a component starting with `.` or ending in `.lock`, a
trailing `/` or `.`, or `HEAD`. `release/2.0` is still a branch name; one git accepts outside that
set, such as a name with `+` or `@`, a leading `_`, or a non-ASCII letter, is not.
`[project] base_branch` and `release_branch` follow the same grammar: `stayfixed.toml` does not
load with either outside it, and the refusal names the key, where
`stayfixed gate` used to blame a `--base` nobody had passed. `plan check` and `test attribute`
compare against `refs/remotes/origin/<base_branch>` by default, spelled in full as `assess`, `gate`
and `adopt promote` spell it, so a tag called `origin/main` no longer stands in for the branch.
