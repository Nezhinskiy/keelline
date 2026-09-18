`keelline detach` now removes the directories the attach created, and not the ones it found.
`.keelline/local/`, `.keelline/`, `.codex/rules/`, `.codex/` and `.claude/` used to survive every
attach-and-detach cycle, so a repository that had been bound once could never be returned to the
state it started in — and the round-trip test could not see it, because it walked files and not
directories.

`attach` records which of those five were absent before its first write, and `detach` removes
exactly that set, last, with `rmdir`. A directory still holding anything at all survives, and so
does its parent; one that predated the attach is not on the record and is never touched; and a
ledger naming a directory no attach could have created is refused with nothing removed, the same
way one naming a foreign file or settings key already was.

The note link tree — ordinarily `docs/memory/` — is the documented exception: it is
repository-configured, so the links are withdrawn and the directory that held them is left.
