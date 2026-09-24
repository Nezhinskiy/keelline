"""The overlay area's `api.py` is held to the same contract every other area's is.

CONTRIBUTING states it once for all of them: "`api.py` is the area's import surface. Other
areas import from it and from nothing else, and its `__all__` must equal exactly what it
imports — a test parses the file and checks."

This area shipped with the install path and without the test, and it is the new surface with
the most consumers — `attach`, `doctor` and `setup` all import from it — so it is the one whose
contract went unasserted longest.
"""

from __future__ import annotations

import keelline.overlay.api as overlay


def test_the_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # An equality and not a subset, for the reason tests/guards/test_surface.py gives: a subset
    # lets an export arrive unnoticed. What each name is doing here is written beside it, so
    # this set states the policy `api.py`'s docstring states rather than freezing today's list.
    # No mutation entry: the mutation is adding an export, which is two lines in `api.py` (the
    # import and the `__all__` entry) and not one substituted line. Measured by hand instead —
    # re-exporting `layout.COMMON` reddens this test and this test alone.
    # The runner is a leaf now (`keelline.runner`); an area's surface does not re-export a
    # leaf, which is why the three names this list used to carry are absent from it.
    required = {
        # creating an overlay and making it this owner's, for setup
        "create",
        "Created",
        "init_instance",
        "Initialised",
        "target_root",
        "require_overlay",
        "overlay_fault",
        # the layout attach reads inside the overlay
        "COMMON_CLAUDE",
        "COMMON_CODEX",
        "COMMON_MEMORY",  # the third of the three; two thirds of a layout invites a hand-spelling
        # the three manifests `init_instance` rewrites, the Codex one included
        "PLUGIN_MANIFEST",
        "MARKETPLACE_MANIFEST",
        "CODEX_PLUGIN_MANIFEST",
        # the shipped template file list, for `scripts/check_artifacts.py` — the one consumer
        # outside `src/`, and the one the wave-3 trim did not see because the boundary walk
        # stopped at `src/`
        "OVERLAY_FILES",
        # the floor an overlay declares and whether a running Keelline meets it, for `doctor`'s
        # `overlay-requires` row (wave 4)
        "requires_of",
        "satisfies",
        # the same reader over two versions, for `upgrade`'s never-backward refusal and
        # `doctor`'s `versions` remedy, so the two agree on direction
        "later",
        # that reader's whole `X.Y.Z` grammar, for `upgrade`'s printing of a recorded version
        "RELEASE",
        # the overlay repository's own sync state, for the `attach` area's session-start
        # handler (wave 4, DC1, DC12)
        "Sync",
        "overlay_sync",
    }
    assert required == set(overlay.__all__)
