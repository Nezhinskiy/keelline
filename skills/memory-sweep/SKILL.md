---
name: memory-sweep
description: Sweep the working-memory store — inventory by size, verify anchors resolve, rewrite notes to rule-plus-pointer, check the link graph and the paths notes name. Use when memory notes have accumulated history or the index has grown.
---

# Sweeping the memory store

1. **Inventory.** Run `keelline memory inventory --json`: every note with its word count,
   type, provenance and staleness. Sort by words, descending; the tail above ~400 words is
   where the value is.
2. **Verify anchors before cutting.** For each note, open the ledger entry behind every
   identifier it names and confirm the pull requests it cites are merged. This is the sweep's
   own job and nothing does it for you: the ledger's scan reads the repository's tracked files
   and skips symlinks, so a store that is git-ignored or linked in is invisible to
   `keelline bugs check`. A pointer to nothing is worse than the retelling it replaced.
3. **Rewrite to rule plus pointer.** Keep the rule, one line of why, how to apply, and a bare
   identifier for the evidence. History belongs to the ledger, the roadmap or the retro.
4. **Merge on close coupling.** Two notes firing on the same trigger, or each needing the
   other to be usable, are one note. A fact mechanized elsewhere is deleted, not kept.
5. **Check the graph.** Run `keelline docs check --memory-graph`: every `[[link]]` resolves,
   no link is immediately repeated, no identifier is bracketed. Advice, not a gate — the
   store is shared by every session on the machine.
6. **Check the pointers out of the store.** Run `keelline memory refs`: every backticked
   repository path a note names still exists. Exit 2 is not a pass with a warning — a
   configured group could not be resolved, so the walk read a subset; fix that before an
   exit 0 means anything. Exit 1 lists paths to fix, or to rewrite in *italics* where the
   note deliberately records a file that is gone.
7. **Regenerate the index.** Run `keelline memory index`, then `keelline memory index --check`.

Conventions for what a note is and how the index routes: [references/protocol.md](references/protocol.md).
