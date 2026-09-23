`keelline detach` can no longer be disabled by a file a clone committed. `.keelline/manifest.json`
is tracked, and `detach` reads it to decide whether the `keelline:ignore` block in `.gitignore`
belongs to `keelline init`'s footprint or to the attach it is undoing — but `Manifest.read`
refuses a manifest that is unreadable, is not a JSON object, or declares a newer format, and
`attach` never opens the file at all. So a clone shipping `{"format": 99}` attached cleanly,
merged your allow rules and hook entries, and then made every `detach` exit 2, above every
withdrawal, for ever.

The same holds for a manifest whose bytes are not UTF-8, one nested deeply enough to exhaust
the JSON parser, and one committed as a symlink out of the repository: each of those made
`detach` stop with an internal error rather than a refusal.

A manifest this command cannot read is now read as no claim of ownership either way: the ignore
block is left alone, which is the conservative half, and everything the attach ledger records is
withdrawn as usual. `--json` reports `ignore_region_removed: false`, and `keelline init` or a
hand edit clears the block.
