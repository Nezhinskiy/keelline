"""What this area publishes. The three checks every surface is held to are
`tests/test_surfaces.py`'s; this list is the one thing that is this area's own."""

from __future__ import annotations

import keelline.docs.api as docs


def test_the_surface_carries_what_every_consumer_reaches_for() -> None:
    # An equality and not a subset, for the reason tests/guards/test_surface.py gives: a subset
    # lets an export arrive unnoticed. No mutation entry: the mutation is adding an export,
    # which is two lines in `api.py` (the import and the `__all__` entry) and not one
    # substituted line. Measured by hand instead — re-exporting `trail.TRAIL_FILE` reddens this
    # test and this test alone.
    #
    # Outside this area, `project` imports `trail_target`, `keelline.assess.gates` imports the
    # three gate functions, `keelline.assess.state` imports `lint` and `declared_state`, and
    # `keelline.assess.tracked` imports `linked_files` and `trail_target`; the other names below
    # have no importer and stay on the argument written beside them in `api.py`.
    required = {
        # the four checks this area is, one call each
        "check_budgets",
        "check_links",
        "check_memory_graph",
        "lint",
        # what `lint` returns: a value a consumer can hold and cannot declare is the one thing
        # a surface exists to prevent
        "Lint",
        # the install path: `project` ships `trail.toml`
        # beside the roadmap and must put it where `docs trail` reads it, a location only
        "trail_target",
        # the three gates keelline.assess.gates runs, each this area's own command's function
        "docs_gate",
        "plan_gate",
        "trail_gate",
        # `adopt begin` asks the trail whether an adoption plan's row declares a state
        "declared_state",
        # `assess` and `adopt promote` ask git whether each file the docs gate reads is tracked,
        # the link targets among them, as this area's link reader finds them
        "linked_files",
    }
    assert required == set(docs.__all__)
