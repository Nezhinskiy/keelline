Cutting a release is now a command rather than a checklist. `keelline release check` holds
one version string across `pyproject.toml`, `uv.lock`, the package, both plugin manifests and
`CHANGELOG.md`, and names every source that disagrees. `keelline release check --tag vX.Y.Z`
adds the tag being cut as one more source — both the plain tag and the platform's own longer
form are accepted, because either may be the ref a run was created from — and at a tag, and
only at a tag, a changelog fragment still waiting to be assembled is a finding too: there is
nothing left to assemble at that point, so a pending fragment means the changelog readers get
is not the one the tag claims. This is Keelline's discipline for its own repository, not
something Keelline asks of yours.

`keelline release notes --version X.Y.Z` assembles `CHANGELOG.md` out of the fragments in
`changelog.d/` through towncrier, and `--draft` prints the section without writing anything or
consuming a fragment. A `--version` that is not the project's own is refused before towncrier
runs, since assembling under another number writes a heading `release check` then rejects; and
a towncrier that cannot be run is reported as the missing development dependency it is rather
than as a traceback.

`keelline release hashes` records the sha256 of the three files a harness executes without
Python — the hook wrapper, the hook entry table and the launcher — into `hooks/hashes.json`
beside them. It is not a release-time command: `keelline release check` compares that record
to the tree on every run, so one of the three edited without re-recording fails the gate in
the same commit rather than at a tag, which is what makes it a record someone has watched
fail. That is the record `keelline doctor`'s `files` row reads on your machine, comparing the
plugin you installed against what the release shipped.
