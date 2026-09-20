"""The C3 import surface: everything a consumer lane may import from this area.

A module and not the package's `__init__`, for one measured reason: `keelline.hooks.registry`
imports `keelline.memory.hooks`, which imports the package first, so a re-export list in
`__init__.py` pulls the whole area — configuration included — into every `discover()` call and
reddens `tests/test_areas.py`. Keeping the surface one level down costs a consumer six
characters and keeps discovery cheap, without a lazy `__getattr__` that would cost every
consumer its types.

**The list is what consumers outside this area import, plus what those names oblige.** That is
a change of rule and not only of length: it used to be what the lanes named in this docstring
were said to need, and this area's own history is what that produces — seventy names, of which
forty-five had no importer anywhere in `src/`, `scripts/` or `tests/`. A lane that needs
something absent from this list grows it deliberately, in a commit that says which lane and why
— it does not import a private module of this area.

Twenty-five names are imported from outside this area today, and the areas that reach for them
are `attach`, `doctor` and `docs`: the resolver and its store (`resolve`, `Store`,
`overlay_root`, `permitted_roots`, `main_checkout`), the overlay layout `attach` writes and
`overlay` renders (`PROJECTS`, `PROJECT_RECORD`, `COMMON_GROUP`), the link tree
(`link`, `attach_main`, `detach_main`, `harness_anchor`, `harness_link_needed`,
`harness_memory_path`, `Links`, `PartialLink`), the bundles `doctor` reports on (`fit`,
`render`, `SLOTS`), the wiki-link grammar and the note walk the graph check reads
(`WIKI_LINK`, `walk`), the binding's git answer (`origin_remote`, `GitUnavailable`), and the
trust region `tests/test_install_path.py` asserts end to end (`DELIMITER`, `markers`).

**Twelve more have no importer and stay, each for a reason written here**, because a name
kept in silence is what made this pass necessary:

- **The types those twenty-five name in their signatures**: `Bundle` and `Fit` (`fit`,
  `render`), `Walk` (`walk`), and `Note` with the `Provenance` inside it, which `Walk` names in
  turn. `tests/test_surfaces.py` derives this rather than restating it, and a return type absent
  from a surface is a value a consumer can hold and cannot declare — the one thing a surface
  exists to prevent.
- **The rest of the trust region's vocabulary**: `wrap`, `new_nonce` and `UnsafeNote`, beside
  the `DELIMITER` and `markers` that already have a caller. Reading such a region needs
  `markers` and `DELIMITER`; producing one needs `wrap` and a nonce from `new_nonce`; a forged
  marker raises `UnsafeNote`. Publishing the reading half and hiding the writing half leaves a
  consumer able to recognise the region and unable to make one, which is the reason
  `attach/api.py` gives for `STATES` and `doctor/api.py` for `STATUSES`: half a closed
  vocabulary cannot be used by the consumer that is handed a value from it.
- **The trust gate**: `may_inject`, `changed`, `TrustState` and `UnreadableTrustRecord`. The
  project's standing constraint is that anything a repository authored reaches a model only
  after `keelline memory trust` and only inside a delimited region; a lane that injects
  repository bytes therefore has to be able to *ask this area* whether it may, to honour §9.4's
  re-prompt predicate — "a store that was trusted and is not any more" — and to tell "this trust
  record is broken" from "this store is not approved", which is the whole point of the class.
  A requirement a consumer cannot import is a requirement with no way to meet it, and this is
  the one group on this list where the cost of being wrong is a repository's bytes reaching a
  model unwrapped.

**Trimmed, in the wave-3 refactor pass: thirty-three names**, every one of them with no importer
in `src/`, `scripts/` or `tests/`, no published signature naming it, and no reader reaching it
by string. Nothing was deleted: each is still where it was written and is reachable from this
area's own module, which is what `memory/commands.py`, `memory/hooks.py` and this area's tests
already do. What went is the claim that another area reads it.

- **The index group** — `INDEX_NAME`, `index_source`, `write_index`, `render_index`,
  `check_index`, `reconcile`, `Reconciliation`, `IndexCheck`. Published because "`worktree.py`
  and `bundles.py` both present `index_source` as *the* place §9.1's per-link target rule
  reaches the index, and neither a reader nor `attach` — the lane that creates the symlinked
  index in the first place — could call it". `attach` shipped and calls none of them; the index
  is a command (`memory index`) and the lanes that want one run it.
- **The notes group** — `read_note`, `render_note`, `with_index`, `write_note`, `NoteError`,
  `NoteType` — published for a `notes` lane, which shipped and imports nothing from here.
  `snapshot`, `refresh_if_trusted` and `Snapshot` went with them: they were published as the
  dance a caller of the exported `write_note` must perform, and with `write_note` gone there is
  no caller on this surface to perform it. That argument comes back with the verb if a lane
  ever needs the verb.
- **The refs group** — `check_refs`, `unresolved`, `audience_violations`, `RefsReport`.
  `docs-tooling` shipped and is a real consumer of this surface; it imports `WIKI_LINK`, `Store`
  and `walk`, and none of these four. The paragraph that said this debt was paid was measuring
  the wrong thing: the lane arriving is not the same as the lane importing.
- **The inventory group** — `inventory`, `totals`, `Entry` — published for `skills-port`, which
  shipped and imports nothing from here.
- **The store predicates** — `in_repository`, `inside_project`, `resolved`, `refusal_reason`,
  `overlay_group_target`. `in_repository` was published "because `inside_project` hands the
  reader to it in as many words", which is this surface citing itself; `refusal_reason` was
  published for an `overlay-hook` lane that does not exist; `overlay_group_target` is read by
  `worktree.py`, one module over, and by nothing else.
- **The leftovers** — `blocks`, `split`, `linked_names`, `harness_link_parts`. Four helpers with
  no argument beside them in the docstring this one replaces, which is how they survived.

`PartialLink` stays: `attach` imports it, which is what the paragraph that argued for it
predicted. `Links` stays for the same reason and is the one name on this list a
`mutations.toml` entry names.
"""

from keelline.memory.bundles import SLOTS, Bundle, Fit, fit, render
from keelline.memory.notes import Note, Provenance, Walk, walk
from keelline.memory.refs import WIKI_LINK
from keelline.memory.store import (
    COMMON_GROUP,
    PROJECT_RECORD,
    PROJECTS,
    GitUnavailable,
    Store,
    main_checkout,
    origin_remote,
    overlay_root,
    permitted_roots,
    resolve,
)
from keelline.memory.trust import (
    DELIMITER,
    TrustState,
    UnreadableTrustRecord,
    UnsafeNote,
    changed,
    markers,
    may_inject,
    new_nonce,
    wrap,
)
from keelline.memory.worktree import (
    Links,
    PartialLink,
    attach_main,
    detach_main,
    harness_anchor,
    harness_link_needed,
    harness_memory_path,
    link,
)

__all__ = [
    "COMMON_GROUP",
    "DELIMITER",
    "PROJECTS",
    "PROJECT_RECORD",
    "SLOTS",
    "WIKI_LINK",
    "Bundle",
    "Fit",
    "GitUnavailable",
    "Links",
    "Note",
    "PartialLink",
    "Provenance",
    "Store",
    "TrustState",
    "UnreadableTrustRecord",
    "UnsafeNote",
    "Walk",
    "attach_main",
    "changed",
    "detach_main",
    "fit",
    "harness_anchor",
    "harness_link_needed",
    "harness_memory_path",
    "link",
    "main_checkout",
    "markers",
    "may_inject",
    "new_nonce",
    "origin_remote",
    "overlay_root",
    "permitted_roots",
    "render",
    "resolve",
    "walk",
    "wrap",
]
