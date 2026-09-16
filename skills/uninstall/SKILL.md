---
name: uninstall
description: Remove Keelline's footprint from a repository, leaving hand-edited files in place and listed. Use when the user asks to uninstall or remove Keelline from a project.
---

# Uninstalling

Written against the CLI contract; the command ships with the `upgrade` lane.

1. Run `keelline uninstall --dry-run` and relay what would be removed, which managed regions
   and marked entries would be taken out, and which hand-edited files would be left in place.
2. Confirm with the user before running `keelline uninstall`; a file left in place needs a
   decision from them, not a `--force`.
3. Relay the list of files left behind exactly as printed.
