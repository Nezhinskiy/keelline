`keelline init` refuses a `keelline.toml` whose `[paths]` aim two of its artifacts at one file —
a `roadmap` and a `roadmap_history` set to the same document, or an `agents_md` pointing at
`CLAUDE.md` — naming the two keys to separate. Before this the run wrote both in order: the
second replaced the first with no verb saying so, `.keelline/manifest.json` recorded two
different digests for one path, and a later `upgrade` would have read one of them as hand-edited
for ever while `uninstall` removed a file holding the other.
