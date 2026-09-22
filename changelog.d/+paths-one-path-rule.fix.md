`keelline init` no longer half-writes a repository over a `[paths]` value it could not write at
all. A value like `docs//roadmap-history.md`, `docs/architecture/` or `./docs` used to pass the
dry run with no refusals and then fail during the real run, after ten files and
`.keelline/manifest.json` were already on disk — and a repository left in that state could not
be re-run, because `init` refuses a manifest it finds and `upgrade` has not shipped. The way out
was deleting `.keelline/` by hand.

Those spellings are now refused before anything is written, by the `[paths]` grammar itself: a
value is a sequence of segments separated by single `/`, no segment empty and no segment that is
just `.` or `..`. A leading `./`, a doubled `//` and a trailing `/` are therefore refused where
they used to be silently normalised away — so a `keelline.toml` that loaded yesterday with one
of them is refused today, naming the key and never quoting the value. `docs/.hidden` and
`docs/..foo` are ordinary names and are still accepted.

The three sentences that promised this — "a refusal anywhere leaves nothing written and no
manifest" — are true again.
