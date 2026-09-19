`keelline release check --tag vX.Y.Z` holds a tag to the same rule as the six version
sources, and refuses a tag while a changelog fragment is still pending; `keelline release
notes --version X.Y.Z` assembles the changelog through towncrier, and refuses a version
that is not the project's.
