"""The release area's `api.py` is held to the same contract every other area's is.

CONTRIBUTING states it once for all of them: "`api.py` is the area's import surface. Other
areas import from it and from nothing else, and its `__all__` must equal exactly what it
imports — a test parses the file and checks."
"""

from __future__ import annotations

import keelline.release.api as release


def test_the_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # An equality and not a subset, for the reason tests/doctor/test_surface.py gives: a subset
    # lets an export arrive unnoticed. `doctor` reads all but `drift` and `RECORD` —
    # `tests/test_manifests.py` reads `drift`, and `scripts/check_artifacts.py` reads
    # `HASHED_FILES` and `RECORD`. `write_record` is deliberately absent, because writing the
    # record is this area's own business and no other lane's.
    required = {
        # what the record covers, and where it lives. This comment used to say `doctor` names
        # the file it compared; it does not, it says "beside `hooks/run-hook.sh`" in prose, so
        # the test was enforcing a dead export against a false premise until the artifact
        # checker stopped spelling all four paths by hand.
        "HASHED_FILES",
        "RECORD",
        # the three answers about a record: what is there, what was recorded, what differs.
        "digests",
        "read_record",
        "drift",
        # "present and not a record" is a distinct answer from "absent" — absent skips in
        # `doctor` and unreadable must be red — so the consumer needs the class to branch on.
        "UnreadableRecord",
    }
    assert required == set(release.__all__)
