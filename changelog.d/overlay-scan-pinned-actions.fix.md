The secret-scan workflow a new overlay ships now pins both GitHub Actions at a full-length commit
sha, with the release each one is in a trailing comment. `actions/checkout@v4` and
`gitleaks/gitleaks-action@v2` were mutable major tags: the code they resolve to is whatever their
owner moves the tag to, in a workflow that runs with your repository's token over the repository
holding your rules and your notes. This is the same argument the overlay's `.pre-commit-config.yaml`
already made about pinning gitleaks itself. Upgrading is a deliberate edit to the sha and the
comment beside it. An existing overlay is not rewritten; `keelline overlay upgrade` offers the
change like any other template change.
