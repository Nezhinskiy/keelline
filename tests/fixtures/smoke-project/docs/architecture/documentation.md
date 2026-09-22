# Documentation policy

Where a fact belongs in this repository, so that a reader — and a session — finds one answer
rather than three.

**One fact has one authoritative home.** Every other document links to it instead of copying
it. A copy is a second thing that can go stale, and nothing tells you which of the two is
current.

**The always-loaded instruction file has budgets.** It is read into every session, so it stays
a map: what this repository is, and links out. Its budgets are in `keelline.toml`, `keelline
docs check` enforces them, and the way to satisfy one is to move detail into the document that
owns it rather than to raise the number.

**Where each kind of fact lives.** Phase history goes in the roadmap. Contracts — interfaces,
invariants, what a component promises — go in the architecture documents. Procedures you would
otherwise re-derive under pressure go in the runbooks. A decision, with the context that forced
it and what it costs, goes in an ADR. A defect goes in the bug ledger, one file per entry.

**Superseded prose is removed in the same change that supersedes it.** Leaving it in place is
how a document comes to describe two designs at once, and a reader has no way to tell which
paragraph won.
