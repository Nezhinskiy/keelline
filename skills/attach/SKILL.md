---
name: attach
description: Bind a repository to its private memory overlay and link the note store in, or detach it. Use when a session reports "not attached", a memory path is a real directory, or the user asks to attach or detach the overlay.
---

# Attaching the overlay

Written against the CLI contract; the command ships with the `attach` lane.

1. Run `keelline attach --store PATH --check` first: it reports whether the overlay's record
   binds this repository's remote and what the permission diff would be, and writes nothing.
2. Relay the diff. Only after the user agrees, run `keelline attach --store PATH`; it writes
   the local settings file and the memory link and prints what it wrote. Pass
   `keelline attach --store PATH --trust-remote` only when the user says the remote should be
   recorded as this project's.
3. `keelline detach` removes the link and the local settings entries; relay what it removed.
