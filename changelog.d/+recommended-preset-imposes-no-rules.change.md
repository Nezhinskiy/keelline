The `recommended` preset no longer carries a `[rules]` table, so the `preset-rules` session-start
bundle is empty for it. stayfixed supports standing rules and imposes none: yours are notes with
`metadata.startup` in your overlay's `common/memory/` or a project's memory, which the
`standing-rules` bundle injects at the start of every session. A preset of your own that carries
a `[rules]` table is still rendered by `preset-rules`. The machine configuration's
`reply_language` and `artifact_language` are still recorded by `stayfixed setup`, but nothing
reads them now: they had a meaning only through the preset's rule about which language each
audience gets. A language preference you want followed is a standing-rule note of your own too.
