# Plans

One implementation plan per work package, `YYYY-MM-DD-<slug>.md`, written against the frozen
extraction design. That design document is not public: it lives in a private repository, and a
plan's references to it cannot be followed from this repository. The principles it argues from,
with their sources, are public in [docs/methodology/](../methodology/README.md). A plan's
`Scope:` line names the package it belongs to and, where that package has them, the contracts
it consumes and produces; a plan the owner cut across several packages — a wave's closure, or
one delivery spanning a lane — names all of them on that line and says why they ship together.
The two P0 documents here were copied from that repository, which keeps its own copies as
history.

Plans dated before 2026-09-28 predate the rename and keep the former name as the record, and
so does the plan that performs it; read `stayfixed` for it in every path, command and variable.

A plan over the plugin directory's 256 KiB file limit continues in `-part-2.md`, `-part-3.md`, …
beside it, which are the same plan: it is cut at a heading, each part ends by linking the next,
each later part opens by naming part 1, and part 1's `Scope:` line governs them all. `stayfixed
plan check` lints each file on its own, so a path one part cites and another declares under
`- Create:` or `- Test:` is reported as a dead reference; across parts that finding is the
split's, not the plan's.
