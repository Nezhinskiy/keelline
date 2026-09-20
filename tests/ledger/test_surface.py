"""What this area publishes. The three checks every surface is held to are
`tests/test_surfaces.py`'s; this list is the one thing that is this area's own."""

from __future__ import annotations

import keelline.ledger.api as ledger


def test_the_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # An equality, for the reason tests/guards/test_surface.py gives: a subset let an export
    # arrive unnoticed. No mutation entry: the mutation is adding an export (two lines).
    # Measured by hand instead — re-exporting `write.file_entry` reddens this test and this
    # test alone.
    #
    # Thirteen names left in the wave-3 refactor pass: the `assess` vocabulary and the writing
    # half with the three return types that came with it. Nothing outside this area imports any
    # name on this list — the six below included — so what stays, stays on the argument written
    # beside it in `api.py`: the two artifacts this area leaves on a project's disk.
    required = {
        # the entry file's grammar, and the error a file that will not parse raises
        "Entry",
        "parse_entry",
        "load_entries",
        "LedgerError",
        # the generated index: writing one, and recognising one already there rather than
        # overwriting a file a person wrote
        "render_index",
        "is_generated_index",
    }
    assert required == set(ledger.__all__)
