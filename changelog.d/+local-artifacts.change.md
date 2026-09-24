An artifact kept out of git with `[artifacts] local` is now written under
`.keelline/local/artifacts/`, and a later run never overwrites or removes one whose bytes are
not what Keelline would write: it is left in place and named, and `--force PATH` takes it.
