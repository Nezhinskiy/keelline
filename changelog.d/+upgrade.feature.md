`stayfixed upgrade [--dry-run] [--force PATH]` refreshes a project's footprint after a
stayfixed update: untouched files are refreshed, edited ones are skipped and named, and
`[stayfixed] version` moves in place with every other byte of `stayfixed.toml` kept. A file
stayfixed never wrote is skipped and named the same way, and `--force` with its path overwrites
it. When the workflow pins stayfixed by commit, `[ci] ref` and the pin move with the version or
none of them does; a `[ci] ref` that is not a commit, such as the `v1` alias, is left as it is,
and only the version moves. A project recording a newer stayfixed is refused, a pre-release
such as `1.0.0-rc1` included, and so is a project recording `1.0.0` under a `1.0.0rc1` build;
so is one whose version does not begin with `X.Y.Z`, or differs from the running one only after
it in a way stayfixed does not order, such as two pre-releases; nothing is written when the plan
refuses anything. A file that cannot be written part-way through stops
the run with what was done kept and recorded, and the next run continues from there.
