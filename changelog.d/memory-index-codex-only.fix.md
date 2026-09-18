`keelline memory session-context --bundle index` now emits on Codex only. Claude Code reads
`MEMORY.md` natively, so injecting it there spent capped `SessionStart` slots on something the
harness already had; Codex has no native auto-memory, which is what the bundle is for. Every
other bundle is unchanged on both harnesses.

This is the one shipped command whose output depends on the ambient environment: the harness is
read from the process's own variables, so the same invocation answers differently inside a Codex
session and a Claude Code one. Nothing else about the command moved — a store that will not
resolve, or a `--store` outside the overlay, is still refused for this bundle on both harnesses.
