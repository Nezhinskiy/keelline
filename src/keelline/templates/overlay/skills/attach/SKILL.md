---
name: attach
description: Bind a repository to this private overlay and link its note store in. Use when a session reports that a repository is not attached, or when the user asks to attach a clone to their overlay.
---

# Attaching a repository to this overlay

1. Find the project's name — the `[project] name` in its `keelline.toml` — and check that
   `projects/<name>/` exists here. If it does not, this repository has not been bound yet and
   the directory is created by the command below.
2. Run `keelline attach --store <this overlay>/projects/<name> --check` first. It reports
   whether the record binds this repository's remote and what permissions would change, and
   writes nothing.
3. Relay that diff. Only after the user agrees, run the same command without `--check`, and
   relay what it wrote.
4. Personal rules, notes and permissions live here and nowhere else. Never copy one into the
   project repository, and never widen a permission on the user's behalf.
