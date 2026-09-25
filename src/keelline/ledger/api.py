"""The import surface: everything a consumer lane may import from this area.

A module and not the package's `__init__`, for the reason `keelline.guards.api` and
`keelline.memory.api` both give: area discovery imports a package before it imports the
submodule it wants, so a re-export list in `__init__.py` would pull this whole area — and with
it the configuration layer — into every `discover()` call. `tests/ledger/test_surface.py`
asserts the `__init__` imports nothing at all.

**Outside this area, `keelline.assess.gates` imports `bugs_gate` and nothing else on this
list**, measured over `src/`, `scripts/` and `tests/`; nothing imported the nineteen names this
list used to hold either. So every other name below is here on an argument rather than on a
caller, and the argument is written beside it.

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

**Trimmed, in the wave-3 refactor pass: thirteen names.** `problems`, `uninitialised`,
`STATUSES`, `SEVERITIES`, `FIXTURE_MARKER`, `ENTRIES_MISSING` and `FOREIGN_CONTENT` were
published against `assess` — "the rule vocabulary and the inertness rule, and the two refusal
messages it reports under its own headings". `next_identifier`, `file_entry` and `renumber`
were "what a lane that files or moves an entry without going through the command calls", and
`Allocation`, `Filed` and `Renumbered` came with them as their return types. No such lane
exists, and no document says which of these names one would reach for. That is the ruling
`overlay/api.py` made about a template tree published against "the release lane will need it"
and `guards/api.py` made again over twenty-nine names published against `assess`: a lane that
does not exist grows this list when it arrives, in a commit that says which lane and why.

The three return types went with their verbs rather than being kept as orphans. The surface
contract requires a type a *published* signature names; with `file_entry`, `next_identifier` and
`renumber` gone, no published signature names `Filed`, `Allocation` or `Renumbered`, and a type
on a surface whose verb is not is a value nobody can be handed. Each is still where it was
written and is reachable from `keelline.ledger.write`, which is what `ledger/commands.py` and
this area's own tests already do.

**What is left is a smaller version of the same question, and it is the owner's.** The six names
of the two artifacts have no importer either. Whether this area publishes at all is a structural
decision and not a refactor's — the previous pass measured that and said so, and this one acts
as far as the rule reaches and leaves the floor standing rather than emptying a list a test
forbids to be empty.

The identifier grammar and the finding shape are **not** here: they are leaves
(`keelline.identifiers`, `keelline.findings`) that three areas share, and a consumer imports
them from there. The surface test pins every export to this area's own modules, so
re-exporting a leaf would redden it.

**`bugs_gate` arrived with the assess lane in wave 5.** It is `(root, config, base) ->
list[Finding]`, the `bugs` gate's whole composition, and `bugs check` answers with the same
function; `problems`, trimmed above, stays behind it in `keelline.ledger.check`.
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
