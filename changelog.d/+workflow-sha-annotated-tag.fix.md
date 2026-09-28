The reusable workflow runs when a caller's `uses:` line names a release tag. `0.1.0`'s tag is
an annotated one, for which the platform reports the tag object rather than the commit, so a
caller pinned to `check.yml@v0.1.0` fails before any gate runs; pin the commit `stayfixed init`
writes, or `@v0.1.1`. The gates are now handed the commit the tag names, which is also what an
upgrade's `[ci] ref` is compared with.
