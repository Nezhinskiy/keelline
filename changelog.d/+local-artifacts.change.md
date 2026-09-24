An artifact kept out of git with `[artifacts] local` is now written under
`.keelline/local/artifacts/`, and what Keelline wrote there is recorded beside it in
`.keelline/local/artifacts.json`, which is kept out of git too. A later run refreshes a copy
nobody changed when a release changes its template, and never overwrites or removes one that
changed since Keelline wrote it: it is left in place and named, and `--force PATH` takes it.
When an artifact's id leaves `[artifacts] local`, its copy there is removed while unchanged
instead of being left behind for `uninstall` to refuse over.
