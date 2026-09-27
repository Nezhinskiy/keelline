"""The import surface: everything a consumer may import from this area.

A module and not the package's `__init__`, for the reason `keelline.guards.api`,
`keelline.memory.api` and `keelline.ledger.api` all give: area discovery imports a package
before it imports the submodule it wants, so a re-export list in `__init__.py` would pull this
whole area — and with it the configuration layer — into every `discover()` call.
`tests/docs/test_surface.py` asserts the `__init__` imports nothing at all.

**Outside this area, `project` imports `trail_target` (the paragraphs on `trail_path` and
`trail_target` say why), `keelline.assess.gates` imports the three gate functions (the last
paragraph) and `keelline.assess.state` imports `lint` and `declared_state`, to check an adoption
plan; nothing imports any other name on this list**, measured over `src/`, `scripts/` and
`tests/`: this area's own tests reach `keelline.docs.plans`, `keelline.docs.hygiene`,
`keelline.docs.graph` and `keelline.docs.trail` directly, and every other area runs the commands.
So every other name below is here on an argument rather than on a caller, and the argument is
written beside it — a surface that survives a trim with no explanation is what made the trim
necessary.

The five besides `trail_target` and the three gate functions are the four checks this area
*is*, one call each, and the one record one of them returns:

- `check_budgets`, `check_links` and `check_memory_graph` each answer one question about the
  documentation tree and return `Finding`s from `keelline.findings`, the leaf three areas
  share — a consumer imports the finding shape from there, not from here.
- `lint` and the `Lint` it returns. A return type absent from this list is a value a consumer
  can hold and cannot declare, and `tests/test_surfaces.py` derives that rule rather than
  restating it; `Lint` is also what keeps this surface above that test's own floor, which
  refuses a surface exporting no function or record at all.

`Finding` and `labels` are **not** here: they are `keelline.findings`', and a consumer imports
them from there.

**The trail half is not here.** The markers, the file name, `Trail`, `read_trail`,
`trail_path`, `render_listing`, `rebuild` and `undeclared_new_documents` stay in
`keelline.docs.trail`, which `docs/commands.py` and this area's own tests reach directly: no
other area reads them, and an area that needs one grows this list, in a commit that says which
area and why.

Of the five names above, `lint` has one importer, `keelline.assess.state`, and the other four
none; they stay on an argument about shape — one call per check rather than the machinery behind
it — and on `tests/test_surfaces.py`'s floor. Whether this area publishes at all is a structural
decision and the owner's; `ledger/api.py` records the same finding about its own list.

**`trail_target`, for the `project` area**, which ships `trail.toml` beside the roadmap template
and must put it where `docs trail` reads it, under the *preset's* `[paths]`, a place this
configuration may never use. It is the location with no disk access, and the engine contains
every target it plans: `trail_path` contains its answer against the root, so asked there it
would refuse whenever that place passed through a symlink, and it stays in
`keelline.docs.trail` for this area's own commands.

**`declared_state`, for `keelline adopt begin`**, which refuses an adoption plan whose trail row
declares no state: a first listing would record it as `delivered` without a word, and the row's
spelling and the trail's reading are this area's.

**Three gate functions, for `keelline assess`.** `docs_gate`, `plan_gate` and
`trail_gate` are each `(root, config, base) -> list[Finding]`, one gate's whole composition.
`keelline assess` runs them as values, and this area's own commands answer with the same
functions (`docs check` with no flag, `docs trail --check`) or with the one call a function
wraps (`plan check` calls `lint`), so a command and its gate cannot drift apart.
"""

from keelline.docs.graph import check_memory_graph
from keelline.docs.hygiene import check_budgets, check_links, docs_gate
from keelline.docs.plans import Lint, lint, plan_gate
from keelline.docs.trail import declared_state, trail_gate, trail_target

__all__ = [
    "Lint",
    "check_budgets",
    "check_links",
    "check_memory_graph",
    "declared_state",
    "docs_gate",
    "lint",
    "plan_gate",
    "trail_gate",
    "trail_target",
]
