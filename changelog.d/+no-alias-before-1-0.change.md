There is no moving `v1` alias to call the reusable workflow at during `0.x`: under semantic
versioning a `0.x` minor may break what the one before it did, so a `0.x` project pins the
full-length commit `stayfixed init` writes, and the `v1` alias arrives with the first `1.x` release.
Until then `stayfixed doctor` reports a `[ci] ref` of `v1` red, as a tag the public repository does
not carry.
