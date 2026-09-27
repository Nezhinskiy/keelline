"""The import surface: everything a consumer lane may import from this area.

A module and not the package's `__init__`, for the reason `keelline.guards.api` and
`keelline.memory.api` both give: area discovery imports a package before it imports the
submodule it wants, so a re-export list in `__init__.py` would pull this whole area — and with
it the configuration layer — into every `discover()` call. `tests/ledger/test_surface.py`
asserts the `__init__` imports nothing at all.

**Outside this area, `keelline.assess.gates` imports `bugs_gate`, and `keelline.project.templates`
(with its tests) imports `render_index` to write a new project's first index, and nothing else on
this list**, measured over `src/`, `scripts/` and `tests/`. So every other name below is here on
an argument rather than on a caller, and the argument is written beside it.

What is left is the two artifacts this area leaves on a project's disk, which outlive any lane
that reads them:

- the entry file's grammar — `parse_entry`, `load_entries` and the `Entry` they yield, with
  `LedgerError` for a file that will not parse. A `raise` is not a signature, so
  `tests/test_surfaces.py` does not derive `LedgerError`; it is here for the reason that check's
  own comment gives about a class reachable only by writing it down.
- the generated index — `render_index`, which writes it from `Entry`s, and
  `is_generated_index`, which recognises one already on disk rather than overwriting a file a
  person wrote. A tool that touches `docs/bug-reports.md` and cannot ask that question is the
  bug this pair exists to prevent.

`Entry` is also what keeps this surface above `tests/test_surfaces.py`'s own floor, which
refuses a surface exporting no function or record at all.

**What is not here.** The rule vocabulary and the refusal messages `bugs check` reports
(`problems` and its constants) stay in `keelline.ledger.check`, and the verbs that file or move an
entry (`file_entry`, `next_identifier`, `renumber`) stay in `keelline.ledger.write` with their
return types: no lane outside this area files or moves an entry without the command, and a type
no published signature names is a value nobody can be handed. A lane that needs one grows this
list, in a commit that says which lane and why.

Of the six names of the two artifacts, only `render_index` has an importer. Whether this area
publishes at all is a structural decision and the owner's; the list stays above the floor
`tests/test_surfaces.py` holds every surface to.

The identifier grammar and the finding shape are **not** here: they are leaves
(`keelline.identifiers`, `keelline.findings`) that three areas share, and a consumer imports
them from there. The surface test pins every export to this area's own modules, so
re-exporting a leaf would redden it.

**`bugs_gate` is `keelline assess`'s.** It is `(root, config, base) -> list[Finding]`, the
`bugs` gate's whole composition, and `bugs check` answers with the same function; `problems`
stays behind it in `keelline.ledger.check`.
"""

from keelline.ledger.check import bugs_gate
from keelline.ledger.entries import Entry, LedgerError, load_entries, parse_entry
from keelline.ledger.index import is_generated_index, render_index

__all__ = [
    "Entry",
    "LedgerError",
    "bugs_gate",
    "is_generated_index",
    "load_entries",
    "parse_entry",
    "render_index",
]
