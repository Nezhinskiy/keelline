`[ci] gate_branch`, left out of `stayfixed.toml`, is `[project] base_branch`, so the workflow
`stayfixed init` renders runs for the repository's own pull requests — whether `init` created the
file or you wrote it with `base_branch = "develop"` and no `[ci]` — and `assess`, `adopt promote`
and the workflow judge against the same branch. Set `gate_branch` to gate another one. A file
that names another base branch and leaves `gate_branch` out gated `main` before; `stayfixed
upgrade` re-renders a caller you have not edited for the base branch, so set `[ci] gate_branch =
"main"` to keep the old one.
