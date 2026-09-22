`keelline init` now writes `CLAUDE.md` pointing at whatever `[paths] agents_md` names, instead of
at the literal `AGENTS.md`. A project that renamed its instruction file — `agents_md =
"CONTEXT.md"` — used to get `CONTEXT.md` written and `CLAUDE.md` pointing at a file that was
never there, with `keelline docs check` passing over the pair, so every Claude Code session in
that repository loaded a dangling pointer and nothing said so.

`CLAUDE.md` is a create-once artifact, so a repository already carrying one is not rewritten: if
yours points at the wrong file, edit that one line by hand.
