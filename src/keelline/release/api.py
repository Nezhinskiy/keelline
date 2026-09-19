"""The release area's import surface: everything another lane may import from it.

`doctor` is the first consumer — `files` compares an installed plugin against the hashes the
release recorded, which needs the file list, the two readers and the class that says "present
and not a record". `RECORD` is not one of `doctor`'s: it names the record's path in prose
instead. The importer for that name is `scripts/check_artifacts.py`, which asks whether a
built sdist carries the three hashed files and the record beside them; before it imported
these two it spelled all four paths again by hand, which is the drift a published constant
exists to stop. `drift` is here for the repository's own manifest test, which holds the
committed record current.

`write_record` is deliberately absent. Writing the record is the release lane's own act, and
`release hashes` is the one caller; a surface that published it would invite a lane to record
a release it is not responsible for.
"""

from keelline.release.hashes import (
    HASHED_FILES,
    RECORD,
    UnreadableRecord,
    digests,
    drift,
    read_record,
)

__all__ = [
    "HASHED_FILES",
    "RECORD",
    "UnreadableRecord",
    "digests",
    "drift",
    "read_record",
]
