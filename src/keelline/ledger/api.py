"""The import surface: everything a consumer lane may import from this area.

A module and not the package's `__init__`, for the reason `keelline.guards.api` and
`keelline.memory.api` both give: area discovery imports a package before it imports the
submodule it wants, so a re-export list in `__init__.py` would pull this whole area — and with
it the configuration layer — into every `discover()` call. `tests/ledger/test_surface.py`
asserts the `__init__` imports nothing at all.

The list is chosen from what the consuming lanes actually reach for. `assess` needs the rule
vocabulary and the inertness rule (`problems`, `uninitialised`, `STATUSES`, `SEVERITIES`,
`FIXTURE_MARKER`) and the two refusal messages it reports under its own headings
(`ENTRIES_MISSING`, `FOREIGN_CONTENT`); `templates` needs the generated-index artifact
(`render_index`, `is_generated_index`) and the entry reader behind it (`Entry`, `parse_entry`,
`load_entries`, `LedgerError`); the writing half (`next_identifier`, `file_entry`, `renumber`)
is what a lane that files or moves an entry without going through the command calls.
`workflows` imports nothing — it runs the command. A lane that needs something absent from
this list grows it deliberately, in a commit that says which lane and why.

`Allocation`, `Filed` and `Renumbered` are here because the three writing verbs return them,
and a return type absent from this list is a value a consumer can hold and cannot declare —
the one thing a surface exists to prevent. They were missing until
`tests/test_surfaces.py` began asking every area the derived question rather than the six
areas that happened to have a copy of it.

**Measured, and not acted on.** Nothing outside this area imports any name on this list — not
one, in `src/`, `scripts/` or `tests/`. Every justification above names `assess` or
`templates`, lanes that do not exist yet, which is the shape `overlay/api.py` ruled out when it
trimmed a template tree published against "the release lane will need it". Trimming to that
ruling empties the list, and an empty surface reddens `test_every_type_the_surface_names_in_a_
signature_is_on_the_surface`'s own non-emptiness floor — so what is left is not a trim but the
structural question of whether this area publishes at all, which is the owner's and not a
refactor's.

The identifier grammar and the finding shape are **not** here: they are leaves
(`keelline.identifiers`, `keelline.findings`) that three areas share, and a consumer imports
them from there. The surface test pins every export to this area's own modules, so
re-exporting a leaf would redden it.
"""

from keelline.ledger.check import problems, uninitialised
from keelline.ledger.entries import (
    SEVERITIES,
    STATUSES,
    Entry,
    LedgerError,
    load_entries,
    parse_entry,
)
from keelline.ledger.index import (
    ENTRIES_MISSING,
    FOREIGN_CONTENT,
    is_generated_index,
    render_index,
)
from keelline.ledger.scan import FIXTURE_MARKER
from keelline.ledger.write import (
    Allocation,
    Filed,
    Renumbered,
    file_entry,
    next_identifier,
    renumber,
)

__all__ = [
    "ENTRIES_MISSING",
    "FIXTURE_MARKER",
    "FOREIGN_CONTENT",
    "SEVERITIES",
    "STATUSES",
    "Allocation",
    "Entry",
    "Filed",
    "LedgerError",
    "Renumbered",
    "file_entry",
    "is_generated_index",
    "load_entries",
    "next_identifier",
    "parse_entry",
    "problems",
    "render_index",
    "renumber",
    "uninitialised",
]
