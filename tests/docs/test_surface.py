"""What this area publishes. The three checks every surface is held to are
`tests/test_surfaces.py`'s; this list is the one thing that is this area's own."""

from __future__ import annotations

import keelline.docs.api as docs


def test_the_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # An equality and not a subset, for the reason tests/guards/test_surface.py gives: a subset
    # lets an export arrive unnoticed. No mutation entry: the mutation is adding an export,
    # which is two lines in `api.py` (the import and the `__all__` entry) and not one
    # substituted line. Measured by hand instead — re-exporting `trail.TRAIL_FILE` reddens this
    # test and this test alone.
    #
    # Ten names left in the wave-3 refactor pass: the trail half, published in one sentence
    # about `templates`, a lane `docs/plans/2026-09-17-wave-3-install-path.md` puts out of
    # scope. Nothing outside this area imports any name on this list — the five below included
    # — so what stays, stays on the argument written beside it in `api.py`.
    required = {
        # the four checks this area is, one call each
        "check_budgets",
        "check_links",
        "check_memory_graph",
        "lint",
        # what `lint` returns: a value a consumer can hold and cannot declare is the one thing
        # a surface exists to prevent
        "Lint",
    }
    assert required == set(docs.__all__)
