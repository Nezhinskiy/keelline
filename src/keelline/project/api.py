"""The import surface: everything a consumer lane may import from this area.

A module and not the package's `__init__`, for the reason `keelline.docs.api`,
`keelline.ledger.api` and `keelline.memory.api` all give: area discovery imports a package
before it imports the submodule it wants, so a re-export list in `__init__.py` would pull this
whole area into every `discover()` call.

Three names, each with the consumer that reaches for it:

- `PROJECT_FILES`, for `scripts/check_artifacts.py`. It asks the built wheel whether the
  twelve shipped template files are actually in it, and before this list existed the only
  other way to ask was to spell twelve paths a second time in the script — which is the drift
  a published constant exists to stop.
- `project_templates` and the `Prepared` it returns, for `tests/project/test_fixture.py`,
  which plans both passes over a copy of the smoke fixture and asserts that the planning has
  nothing left to create, that every artifact the fixture's manifest records is one the plan
  recognises as already correct, and that every provenance it records is the one this build
  would write. Not that the fixture is what these templates render, which is what this line
  used to say: five of the fixture's files are its own — a bug index listing `BR-001`, a
  roadmap, its history, the trail, the runbook — and come back `skip_modified` with bytes that
  differ from the templates. That module's docstring states the measurement. A return type
  absent from this list is a value a consumer can hold and cannot declare, and
  `tests/test_surfaces.py` derives that rule rather than restating it.

`read`, `fill`, `GATE_BRANCH`, `HARNESS_REGION` and `CI_WORKFLOW` are **not** here: they are
this area's own, reached by `keelline.project.templates` and by nothing outside it. A lane that
needs one grows this list deliberately, in a commit that says which lane and why.
"""

from keelline.project.layout import PROJECT_FILES
from keelline.project.templates import Prepared, project_templates

__all__ = [
    "PROJECT_FILES",
    "Prepared",
    "project_templates",
]
