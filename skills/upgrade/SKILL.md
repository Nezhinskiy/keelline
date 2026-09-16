---
name: upgrade
description: Upgrade the Keelline footprint in a repository after a plugin update, keeping every hand edit. Use when the user asks to upgrade, update or refresh Keelline's files, or after the plugin version changed.
---

# Upgrading the footprint

Written against the CLI contract; the command ships with the `upgrade` lane and is not
available yet. If an invocation below is rejected as an unknown command, say so and
stop — do not improvise a substitute.

1. Run `keelline upgrade --dry-run` and relay each artifact with its verdict: update, skip
   (hand-edited), new, or remove — plus the migrations that would run and the `[ci] ref` it
   would bump to.
2. A skipped file is one the user edited; ask before passing `keelline upgrade --force PATH`
   for it, and never force a path the user did not name.
3. Run `keelline upgrade`, then relay what it wrote. On Codex, relay which hooks now need
   re-trusting.
