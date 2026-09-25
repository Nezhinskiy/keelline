`keelline init`, `upgrade` and `uninstall` refuse a `keelline.toml` whose `[paths]` aim two of
its artifacts at one file, before anything is written, naming the two artifacts and the keys to
separate: two of one pass — a `roadmap` and a `roadmap_history` set to the same document, or an
`agents_md` pointing at `CLAUDE.md` — or one artifact at a file another is built to write, such as
`roadmap = "CLAUDE.md"`. Paths that differ only in case are one file here, as they are on macOS
and Windows. Only the `AGENTS.md` skeleton and the region inside it share a file by design. Before
this `init` wrote both in order: the second replaced the first with no verb saying so,
`.keelline/manifest.json` recorded two different digests for one path, and a later `upgrade`
would have read one of them as hand-edited for ever while `uninstall` removed a file holding the
other.
