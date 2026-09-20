"""What this area publishes. The three checks every surface is held to are
`tests/test_surfaces.py`'s; this list is the one thing that is this area's own."""

from __future__ import annotations

import keelline.ledger.api as ledger


def test_the_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # An equality, for the reason tests/guards/test_surface.py gives: a subset let an export
    # arrive unnoticed. No mutation entry: the mutation is adding an export (two lines).
    required = {
        "Entry",
        "LedgerError",
        # the three writing verbs' return types: a value a consumer can hold and cannot
        # declare is the one thing a surface exists to prevent, and these were missing until
        # `tests/test_surfaces.py` asked every area the derived question instead of six of them
        "Allocation",
        "Filed",
        "Renumbered",
        "STATUSES",
        "SEVERITIES",
        "FIXTURE_MARKER",
        "ENTRIES_MISSING",
        "FOREIGN_CONTENT",
        "parse_entry",
        "load_entries",
        "render_index",
        "is_generated_index",
        "uninitialised",
        "problems",
        "next_identifier",
        "file_entry",
        "renumber",
    }
    assert required == set(ledger.__all__)
