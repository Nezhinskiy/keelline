`[ci] gate_branch`, left out of `keelline.toml`, is `[project] base_branch`, so the workflow
`keelline init` renders runs for the repository's own pull requests — whether `init` created the
file or you wrote it with `base_branch = "develop"` and no `[ci]` — and `assess`, `adopt promote`
and the workflow judge against the same branch. Set `gate_branch` to gate another one.
