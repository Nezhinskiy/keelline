"""The import surface: everything a consumer lane may import from this area.

A module and not the package's `__init__`, for the reason `keelline.guards.api`,
`keelline.memory.api` and `keelline.ledger.api` all give: area discovery imports a package
before it imports the submodule it wants, so a re-export list in `__init__.py` would pull this
whole area — and with it the configuration layer — into every `discover()` call.
`tests/docs/test_surface.py` asserts the `__init__` imports nothing at all.

The list is chosen from what the consuming lanes actually reach for. `assess` runs every check
as a library call rather than as a subprocess and therefore needs `check_budgets`,
`check_links`, `check_memory_graph` and `lint` with the `Lint` it returns; `templates` writes
the roadmap skeleton and the first `trail.toml`, so it needs the markers and the file name
(`TRAIL_MARKER`, `STATUS_HEADING`, `END_MARKER`, `TRAIL_FILE`) and the regeneration path
(`read_trail`, `trail_path`, `render_listing`, `rebuild`, `undeclared_new_documents`, `Trail`).
`workflows` imports nothing — it runs the commands. A lane that needs something absent from
this list grows it deliberately, in a commit that says which lane and why.

`Finding` and `labels` are **not** here: they are `keelline.findings`', a leaf three areas
share, and a consumer imports them from there. The marker is exported once, as `TRAIL_MARKER`
— `docs.trail`'s `MARKER` is a local alias for the same constant, and putting both on this
list would offer two names for one literal.
"""

from keelline.docs.graph import check_memory_graph
from keelline.docs.hygiene import STATUS_HEADING, TRAIL_MARKER, check_budgets, check_links
from keelline.docs.plans import Lint, lint
from keelline.docs.trail import (
    END_MARKER,
    TRAIL_FILE,
    Trail,
    read_trail,
    rebuild,
    render_listing,
    trail_path,
    undeclared_new_documents,
)

__all__ = [
    "END_MARKER",
    "STATUS_HEADING",
    "TRAIL_FILE",
    "TRAIL_MARKER",
    "Lint",
    "Trail",
    "check_budgets",
    "check_links",
    "check_memory_graph",
    "lint",
    "read_trail",
    "rebuild",
    "render_listing",
    "trail_path",
    "undeclared_new_documents",
]
