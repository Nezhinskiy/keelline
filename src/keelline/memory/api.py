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

Two groups were absent and are now here, because the list has to be usable, not merely
plausible. `wrap` was exported without `new_nonce`, `markers`, `DELIMITER` or `UnsafeNote`,
which are exactly what a caller needs to produce a nonce, recognise the region it created and
catch the refusal a forged marker raises — so the one lane that would need `wrap` (one wrapping
its own repository content) could not use it without importing the private module this
docstring forbids. And `Reconciliation`, `IndexCheck`, `Fit` and `Walk` are the return types of
the exported `reconcile`, `check_index`, `fit` and `walk`: without them a typed consumer cannot
annotate what it is handed.

`PartialLink` is here for the same reason, and for `attach`, the lane named above as the one
that "binds and links". `link` raises it when a write fails part-way, carrying the links it did
make; a consumer can catch it as the `OSError` it is without this export, but reading
`.created` — the whole reason it exists rather than a bare `OSError` — would otherwise mean
importing `keelline.memory.worktree`, which this docstring forbids.

`Links` is the same rule again, and it arrived late because `link` used to return
`list[Path]`: the call that withdraws the harness link when trust lapses gave it
`Links(created, revoked)` instead, and a return type absent from this list is a value `attach`
can hold and cannot declare. The list below is now checked against the signatures rather than
only against itself — see `tests/memory/test_surface.py`, whose hand-written `required` set
could not notice a name nobody had added to either side.

**A name this list points at must be on it.** Three were not, and each is a place an exported
docstring sends the reader by name — which is the same failure the `wrap`/`new_nonce` addition
above closed, one function over:

- `in_repository`, because `inside_project` hands the reader to it in as many words. The two
  answer different questions (a store's notes, versus one particular file the store yields),
  and a consumer that injects a specific file — `MEMORY.md`, anything that belongs to no group
  — needs the second one.
- `index_source` and `INDEX_NAME`, because `worktree.py` and `bundles.py` both present
  `index_source` as *the* place §9.1's per-link target rule reaches the index, and neither a
  reader nor `attach` — the lane that creates the symlinked index in the first place — could
  call it.
- `snapshot`, `refresh_if_trusted` and `Snapshot`, because `write_note` is exported and
  `store_digest` covers every note. A lane that rewrites a note in a trusted store therefore
  revokes the record it depends on, silently, exactly as `memory index` used to: the store
  stays put, every bundle goes empty and nothing says why. The dance that fixes it — snapshot
  before the write, `refresh_if_trusted` after with the paths this run authored — is not
  reconstructible from the rest of this surface, so it is part of it.

**Three more, from the same rule that a name this list points at must be on it.**
`trust.changed` and the `TrustState` it reads are §9.4's re-prompt predicate — "a store that was
trusted and is not any more" — and neither was exported, so no consumer could reach the
distinction they implement, and `TrustState.recorded` had no reader in production at all. A
predicate a lane is required to honour and cannot import is a requirement with no way to meet
it. `UnreadableTrustRecord` joins them because `state` and `may_inject` now raise it: a consumer
that catches `Refusal` broadly is fine, but one that wants to tell "this record is broken" from
"this store is not approved" — which is the whole point of the class — needs the name.

**The debt this list recorded is paid.** `docs-tooling` is a consumer of C3, and the row this
paragraph used to hold open — a reference guard this lane planned and never shipped — is now
`refs.py`: `WIKI_LINK`, `RefsReport`, `unresolved`, `audience_violations` and `check_refs` are
on the list below. `WIKI_LINK` is here rather than in the docs area because a wiki-link is this
lane's grammar, and the graph check reads it from this surface instead of spelling a second
one. The name shipped is `check_refs`, not the `refs.check` the old paragraph promised: `check`
alone says nothing at the point of import.
"""

from keelline.memory.bundles import SLOTS, Bundle, Fit, blocks, fit, render, split
from keelline.memory.index import (
    INDEX_NAME,
    IndexCheck,
    Reconciliation,
    check_index,
    index_source,
    reconcile,
    render_index,
    write_index,
)
from keelline.memory.inventory import Entry, inventory, totals
from keelline.memory.notes import (
    Note,
    NoteError,
    NoteType,
    Provenance,
    Walk,
    read_note,
    render_note,
    walk,
    with_index,
    write_note,
)
from keelline.memory.refs import (
    WIKI_LINK,
    RefsReport,
    audience_violations,
    check_refs,
    unresolved,
)
from keelline.memory.store import (
    Store,
    in_repository,
    inside_project,
    main_checkout,
    overlay_root,
    permitted_roots,
    refusal_reason,
    resolve,
    resolved,
)
from keelline.memory.trust import (
    DELIMITER,
    Snapshot,
    TrustState,
    UnreadableTrustRecord,
    UnsafeNote,
    changed,
    markers,
    may_inject,
    new_nonce,
    refresh_if_trusted,
    snapshot,
    wrap,
)
from keelline.memory.worktree import Links, PartialLink, link, linked_names

__all__ = [
    "DELIMITER",
    "INDEX_NAME",
    "SLOTS",
    "WIKI_LINK",
    "Bundle",
    "Entry",
    "Fit",
    "IndexCheck",
    "Links",
    "Note",
    "NoteError",
    "NoteType",
    "PartialLink",
    "Provenance",
    "Reconciliation",
    "RefsReport",
    "Snapshot",
    "Store",
    "TrustState",
    "UnreadableTrustRecord",
    "UnsafeNote",
    "Walk",
    "audience_violations",
    "blocks",
    "changed",
    "check_index",
    "check_refs",
    "fit",
    "in_repository",
    "index_source",
    "inside_project",
    "inventory",
    "link",
    "linked_names",
    "main_checkout",
    "markers",
    "may_inject",
    "new_nonce",
    "overlay_root",
    "permitted_roots",
    "read_note",
    "reconcile",
    "refresh_if_trusted",
    "refusal_reason",
    "render",
    "render_index",
    "render_note",
    "resolve",
    "resolved",
    "snapshot",
    "split",
    "totals",
    "unresolved",
    "walk",
    "with_index",
    "wrap",
    "write_index",
    "write_note",
]
