`keelline upgrade [--dry-run] [--force PATH]` refreshes a project's footprint after a
Keelline update: untouched files are refreshed, edited ones are skipped and named, and
`[keelline] version` moves in place with every other byte of `keelline.toml` kept. When the
workflow pins Keelline by commit, `[ci] ref` and the pin move with the version or none of
them does. A project recording a newer Keelline is refused, a pre-release such as
`1.0.0-rc1` included, and so is one whose version does not begin with `X.Y.Z`; nothing is
written when the plan refuses anything. A file that cannot be written part-way through stops
the run with what was done kept and recorded, and the next run continues from there.
