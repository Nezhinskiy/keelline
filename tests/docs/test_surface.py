from __future__ import annotations

import keelline.docs.api as docs


def test_the_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # The marker is here once, as `TRAIL_MARKER`: `docs.trail`'s `MARKER` is a module-local
    # alias for the same literal, and exporting both would put two names on one constant.
    required = {
        "TRAIL_MARKER",
        "STATUS_HEADING",
        "END_MARKER",
        "TRAIL_FILE",
        "Trail",
        "Lint",
        "check_budgets",
        "check_links",
        "check_memory_graph",
        "read_trail",
        "trail_path",
        "render_listing",
        "rebuild",
        "undeclared_new_documents",
        "lint",
    }
    assert required == set(docs.__all__)
