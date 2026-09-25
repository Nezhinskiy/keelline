The reusable `check.yml` workflow no longer lets the pull request it checks decide whether its
gates enforce. The step that reads the base branch's `keelline.toml` ran `python3 -c "import
tomllib"` inside the caller's checkout, and `python3 -c` puts the working directory first on the
import path — so a pull request that added a `tomllib.py` (or a `tomllib/` package) at the
repository's top supplied the reader, chose the state it reported, and with `installed` read as
anything else turned every gate advisory and the job green. `keelline.toml` itself stayed
untouched, so the rule that refuses a changed configuration had nothing to see.

The step now runs `python3 -P`, which leaves the working directory off the import path; the
standard library's `tomllib` reads the base's configuration whatever the tree under review
contains. The gate steps themselves were never exposed: they run from the workspace root, which
the caller's checkout cannot write into.
