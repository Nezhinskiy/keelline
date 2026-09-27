`keelline doctor`'s `ci-ref` row no longer reports green for a repository with no CI workflow in
it. With `[ci] mode = "reusable"`, a released commit recorded in `[ci] ref` and no
`.github/workflows/keelline.yml`, the row said "[ci] ref is a released Keelline commit" — which
reads as "my gate is pinned correctly" when no gate exists at all. That is the state `init`
itself leaves whenever it reports the workflow under `skipped`, and the state you reach by
deleting the file.

It is now a warning that says the ref is recorded and the workflow is not there, with a remedy.
Under `[ci] mode = "none"` or `"uvx"` this build renders no workflow, so an absent one is the
configuration working and the row still reports what the ref itself is.
