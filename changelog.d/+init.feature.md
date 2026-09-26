`keelline init --yes` writes a repository's footprint: `keelline.toml` from what it can detect —
the project's name from `origin`, its base branch, which agent surfaces it carries — a
`CLAUDE.md` pointer, an `AGENTS.md` skeleton where there is none and a managed section where
there is one, a `.gitignore` block, the documentation skeleton the other commands expect, and,
once a release exists, a CI workflow that calls the reusable gate pinned to the commit of the
release that wrote it. Every file it writes is a scaffold artifact recorded in
`.keelline/manifest.json`, the written-once ones included, so a later `keelline upgrade` can
tell what you have touched from what you have not — a file that was already there is left alone
and recorded nowhere, which is how the `keelline.toml` of an adopted repository stays yours,
gaining at most a missing `[keelline] version`. A `keelline.toml` you wrote by hand is read as
the answers rather than replaced — a `note:` names the custom gates it configures, whose
commands `keelline assess` runs, and a symlinked one is refused rather than followed —
`--dry-run` shows every file before one is written, and a refusal anywhere writes nothing. `--no-ci` writes no workflow and asks no remote for a pin,
recording `[ci] mode = "none"` in the document when this run is the one that writes it. Until
the first release there is no commit to pin and the workflow is skipped with a sentence saying
so — or saying that the repository could not be asked.
