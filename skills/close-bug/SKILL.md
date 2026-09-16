---
name: close-bug
description: Close a bug ledger entry correctly — frontmatter, Fix section, index regeneration, and the checks that catch a half-closed entry. Use when marking a ledger entry fixed, partial, or rejected.
---

# Closing a ledger entry

1. Open the entry file under the project's ledger directory (`[paths] bugs` in
   `keelline.toml`). Set `status:` to `fixed` / `partial` / `rejected` and `fixed_in:` to the
   commit, pull request or branch — **double-quoted around the backticks**
   (``fixed_in: "`abc1234`"``); written bare, both `index` and `check` refuse it.
2. Append a `## Fix` section stating what changed, **which real, existing test covers it**
   (open the path to be sure it exists), and what was deliberately not changed.
3. If the entry's evidence-boundary line is now settled, say so there rather than deleting it.
4. Run `keelline bugs index` — never hand-edit the generated index.
5. Run `keelline bugs check`; a `stale-index` or `dangling-mention` label names what is left,
   and `--json` carries the detail.

A number claimed by two branches is moved with `keelline bugs renumber OLD NEW`, which rewrites
every reference and leaves a pointer at the old number. The project's ledger runbook, if it
has one, holds the merge procedure.
