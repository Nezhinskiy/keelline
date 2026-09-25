`keelline init --yes` takes the base branch from `origin/HEAD` only when it names a plain branch;
any other name the remote reported is replaced by `main` rather than written into
`keelline.toml`.
