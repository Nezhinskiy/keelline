"""The attach area's `api.py` is held to the same contract every other area's is.

CONTRIBUTING states it once for all of them: "`api.py` is the area's import surface. Other
areas import from it and from nothing else, and its `__all__` must equal exactly what it
imports — a test parses the file and checks."
"""

from __future__ import annotations

import keelline.attach.api as attach


def test_the_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # An equality and not a subset, for the reason tests/guards/test_surface.py gives: a subset
    # lets an export arrive unnoticed. What each name is doing here is written beside it, so
    # this set states the policy `api.py`'s docstring states — a name is on the surface because
    # a consumer outside this area reaches for it, or because an exported name's signature or
    # vocabulary requires it — rather than freezing whatever the list happened to hold. The
    # wave-3 review found it holding twelve names with no consumer at all, three of which are
    # below with the argument for keeping them and three of which left.
    #
    # Four more left in the wave-3 refactor pass — `attach`, `detach`, `Attached`, `Detached`.
    # They were kept by a sentence saying this walkthrough "drives `attach` and `detach`":
    # `tests/test_install_path.py` drives the argument parser and imports two surfaces,
    # `keelline.doctor.api` and `keelline.memory.api`, neither of them this one.
    #
    # No mutation entry: the mutation is adding an export, which is two lines in `api.py` (the
    # import and the `__all__` entry) and not one substituted line. Measured by hand instead —
    # re-exporting `permissions.check` reddens this test and this test alone.
    required = {
        # the ledger, the binding and the overlay's granted entries, for doctor
        "LEDGER",
        "ledger",
        "AttachLedger",  # what `ledger` returns; doctor cannot annotate it otherwise
        "read_binding",
        "Binding",
        "MISMATCH",
        "overlay_entries",
        "LOCAL_SETTINGS",  # the file those entries live in
        # the rest of `Binding.state`'s closed vocabulary: doctor branches on MISMATCH, and a
        # consumer that can recognise the bad state and cannot name the good ones is the reason
        # this set is the export rather than the member that had a caller first
        "BOUND",
        "UNBOUND",
        "STATES",
        # the `.gitignore` region's name and body, for `init` (wave 4, DC4): one spelling
        "IGNORE_REGION",
        "IGNORE_BODY",
    }
    assert required == set(attach.__all__)
