"""The C3 import surface: everything a consumer lane may import from this area.

A module and not the package's `__init__`, for one measured reason: `keelline.hooks.registry`
imports `keelline.memory.hooks`, which imports the package first, so a re-export list in
`__init__.py` pulls the whole area — configuration included — into every `discover()` call and
reddens `tests/test_areas.py`. Keeping the surface one level down costs a consumer six
characters and keeps discovery cheap, without a lazy `__getattr__` that would cost every
consumer its types.

Everything a consumer lane needs is re-exported here, and the list is chosen from what those
lanes actually reach for rather than from what this lane happens to find tidy: `attach` binds
and links, `notes` rewrites notes, `mcp` needs the same binding predicate the resolver uses,
`overlay-hook` needs the refusal line, `skills-port` needs the inventory, and `hooks-core` needs
the bundle slots. A lane that needs something absent from this list grows it deliberately, in a
commit that says which lane and why.
"""

from keelline.memory.bundles import SLOTS, Bundle, blocks, fit, render, split
from keelline.memory.index import check_index, reconcile, render_index, write_index
from keelline.memory.inventory import Entry, inventory, totals
from keelline.memory.notes import (
    Note,
    NoteError,
    NoteType,
    Provenance,
    read_note,
    render_note,
    walk,
    with_index,
    write_note,
)
from keelline.memory.store import (
    Store,
    inside_project,
    main_checkout,
    overlay_root,
    permitted_roots,
    refusal_reason,
    resolve,
)
from keelline.memory.trust import may_inject, wrap
from keelline.memory.worktree import link, linked_names

__all__ = [
    "SLOTS",
    "Bundle",
    "Entry",
    "Note",
    "NoteError",
    "NoteType",
    "Provenance",
    "Store",
    "blocks",
    "check_index",
    "fit",
    "inside_project",
    "inventory",
    "link",
    "linked_names",
    "main_checkout",
    "may_inject",
    "overlay_root",
    "permitted_roots",
    "read_note",
    "reconcile",
    "refusal_reason",
    "render",
    "render_index",
    "render_note",
    "resolve",
    "split",
    "totals",
    "walk",
    "with_index",
    "wrap",
    "write_index",
    "write_note",
]
