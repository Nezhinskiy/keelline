`init`, `upgrade` and `uninstall` refuse an `[artifacts] local` list naming `config` or
`gitignore` before writing anything: every command reads `keelline.toml` at the repository root,
and the ignore block there is what keeps `.keelline/local/` out of git, so a copy of either kept
out of git would never be read.
