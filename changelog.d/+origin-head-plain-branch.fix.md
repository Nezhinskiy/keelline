`keelline init --yes` takes the base branch from `origin/HEAD` only when it names a plain branch
under `refs/remotes/origin/`; any other name the remote reported is replaced by `main` rather than
written into `keelline.toml`, and the report says so in a `note:` line without repeating the name.
A tag or a local branch called `origin/<branch>` no longer turns the base branch into
`remotes/origin/<branch>`. With no `origin/HEAD` — a repository nobody cloned — the branch checked
out is the base branch, with a `note:` when it is not `main`.
