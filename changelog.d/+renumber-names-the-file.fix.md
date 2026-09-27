`keelline bugs renumber` names the file it could not sweep, not a prefix of it. A path holding a
colon was cut at the colon, so a file under `docs/a:b/` was reported as `docs/a`, a directory the
operator would look in for nothing. The `--json` `unswept` list is unchanged: one `"path: reason"`
string per file.
