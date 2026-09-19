`keelline release check --tag vX.Y.Z` holds a tag to the same rule as the six version
sources, and refuses a tag while a changelog fragment is still pending; `keelline release
notes --version X.Y.Z` assembles the changelog through towncrier, and refuses a version
that is not the project's.

`keelline release hashes` records the sha256 of the three files the harness executes without
Python — the hook wrapper, the hook entry table and the launcher — into `hooks/hashes.json`
beside them, and `keelline release check` compares the record to the tree on every run, so a
shipped file edited without re-recording fails the gate in the same commit rather than at a tag.
