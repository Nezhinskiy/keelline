`keelline attach` now refuses, before it writes anything, when one of the repository's note
groups is still a real directory rather than a link into the overlay: linking over it would
have left the session reading the repository's copy while the overlay's share stayed empty,
with the binding record and the settings merge already written. `keelline attach --check`
reports how many such groups there are and exits 1, so the notes can be moved first.
`keelline detach` leaves the `.gitignore` block in place on a repository `keelline init` set
up, because the manifest records that block as the footprint's and not the attach's.
