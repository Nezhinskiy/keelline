`keelline init` in a repository whose base branch is not `main` writes that branch as
`[ci] gate_branch` too, so the workflow it renders runs for the repository's own pull requests.
A `keelline.toml` you wrote keeps its own `[ci]`.
