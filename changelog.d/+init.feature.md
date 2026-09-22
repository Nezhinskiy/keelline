`keelline init --yes` writes a repository's footprint: `keelline.toml` from what it can detect
— the project's name from `origin`, its base branch, which agent surfaces it carries — a
`CLAUDE.md` pointer, an `AGENTS.md` skeleton where there is none and a managed section where
there is one, a `.gitignore` block, the documentation skeleton the other commands expect, and,
once a release exists, a CI workflow that calls the reusable gate pinned to the commit of the
release that wrote it. Every file is a scaffold artifact recorded in `.keelline/manifest.json`,
the three written-once ones included, so a later `upgrade` (ships later) can tell what you
have touched from what you have not. A `keelline.toml` you wrote by hand is read as the
answers rather than replaced, `--dry-run` shows every file before one is written, and a
refusal anywhere writes nothing. Until the first release there is no commit to pin and the
workflow is skipped with a sentence saying so — or saying that the repository could not be
asked.
