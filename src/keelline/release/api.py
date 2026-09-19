"""The release area's import surface: everything another lane may import from it.

`doctor` is the consumer this exists for — §8.4 has `files` compare an installed plugin
against the hashes the release recorded, which needs the file list, the record's path, the
two readers and the class that says "present and not a record". `drift` is here for the
repository's own manifest test, which holds the committed record current.

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
