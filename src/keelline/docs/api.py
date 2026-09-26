"""The import surface: everything a consumer lane may import from this area.

A module and not the package's `__init__`, for the reason `keelline.guards.api`,
`keelline.memory.api` and `keelline.ledger.api` all give: area discovery imports a package
before it imports the submodule it wants, so a re-export list in `__init__.py` would pull this
whole area — and with it the configuration layer — into every `discover()` call.
`tests/docs/test_surface.py` asserts the `__init__` imports nothing at all.

**Outside this area, `project` imports `trail_target` (the paragraphs on `trail_path` and
`trail_target` say why), `keelline.assess.gates` imports the three gate functions (the last
paragraph) and `keelline.assess.state` imports `lint`, to check an adoption plan; nothing imports
any other name on this list**, measured over `src/`, `scripts/` and `tests/`: this area's own
tests reach `keelline.docs.plans`, `keelline.docs.hygiene`, `keelline.docs.graph` and
`keelline.docs.trail` directly, and every other lane runs the commands. So every other name below
is here on an argument rather than on a caller, and the argument is written beside it — a surface
that survives a trim with no explanation is what made the trim necessary.

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

**Trimmed, in the wave-3 refactor pass: the trail half, ten names.** `TRAIL_MARKER`,
`STATUS_HEADING`, `END_MARKER`, `TRAIL_FILE`, `Trail`, `read_trail`, `trail_path`,
`render_listing`, `rebuild` and `undeclared_new_documents` were published in one sentence —
"`templates` writes the roadmap skeleton and the first `trail.toml`, so it needs the markers and
the file name and the regeneration path". `templates` does not exist;
`docs/plans/2026-09-17-wave-3-install-path.md` says the lane that would have shipped one "is out
of scope", and no document anywhere says which of these names it would reach for. That is the
ruling `overlay/api.py` made about a template tree published against "the release lane will need
it", and `guards/api.py` made again over twenty-nine names published against `assess`: a lane
that does not exist yet grows this list when it arrives, in a commit that says which lane and
why. Each of the ten is still where it was written and is reachable from `keelline.docs.trail`,
which is what `docs/commands.py` and this area's own tests already do; what went is the claim
that another area reads it.

**What is left is a smaller version of the same question, and it is the owner's.** Of the five
names above, `lint` has one importer, `keelline.assess.state`, and the other four none; they
survive this pass on an argument about shape — one call per check rather than the machinery
behind it — and on `tests/test_surfaces.py`'s floor. Whether this area publishes at all is a
structural decision, not a refactor's; `ledger/api.py` records the same finding about its own
list.

**`trail_path` returns, in wave 4.** The lane the wave-3 trim named as absent now exists: the
`project` area ships `trail.toml` beside the roadmap template and must put it where `docs
trail` reads it. The other nine trimmed names have no consumer yet and stay where they were
written, reachable from `keelline.docs.trail`.

**And gives way to `trail_target`, in wave 5.** `trail_path` contains its answer against the
root, so the project area asking where the trail goes under the *preset's* `[paths]`, a place
this configuration may never use, was refused whenever that place passed through a symlink. What
the project area needs is the location, and the engine contains every target it plans;
`trail_target` is that location, with no disk access, and `trail_path` stays in
`keelline.docs.trail` for this area's own commands.

**And grows by three gate functions, for `keelline assess`.** `docs_gate`, `plan_gate` and
`trail_gate` are each `(root, config, base) -> list[Finding]`, one gate's whole composition.
`keelline assess` runs them as values, and this area's own commands answer with the same
functions (`docs check` with no flag, `docs trail --check`) or with the one call a function
wraps (`plan check` calls `lint`), so a command and its gate cannot drift apart.
"""

from keelline.docs.graph import check_memory_graph
from keelline.docs.hygiene import check_budgets, check_links, docs_gate
from keelline.docs.plans import Lint, lint, plan_gate
from keelline.docs.trail import trail_gate, trail_target

__all__ = [
    "Lint",
    "check_budgets",
    "check_links",
    "check_memory_graph",
    "docs_gate",
    "lint",
    "plan_gate",
    "trail_gate",
    "trail_target",
]
