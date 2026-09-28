`stayfixed bugs renumber` no longer names the wrong file when it could not sweep one. It rebuilt the
path by cutting its message at the first colon, so a file under `docs/a:b/` was reported as
`docs/a`, a directory the operator would look in for nothing. A colon is outside the names a
summary line prints as themselves, so such a path is now withheld on the line as
`<unprintable name; see --json>` and named whole in `--json`'s `unswept`.
