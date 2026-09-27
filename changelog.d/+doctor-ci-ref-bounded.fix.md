`keelline doctor` can no longer be stopped, or delayed for five minutes, by the repository it is
reporting on.

The `ci-ref` row reads `.github/workflows/keelline.yml` to compare the ref the workflow pins with
the one `keelline.toml` records, and that path is the repository's: a clone chooses what sits
there. The read asked nothing about what it was opening, so a committed symlink to a FIFO made it
block with nothing to read and `doctor` never returned at all — on a command that is otherwise one
line of output and has no timeout of its own. The path is now read only when it is a regular file
and only to a 256 KiB bound, the two guards the `hook-entries` and `diagnostics` rows already had.
Anything else there — a directory, a link to a FIFO, a dangling link, a file past the bound — is a
warning that names the path and never the workflow's agreement, and a byte that is not UTF-8 is
replaced rather than raised: it used to arrive as `ci-ref: red — this check could not run`, and
exit 1, which a clone could force.

The same row's `git ls-remote` against the public repository's tags is bounded at 30 seconds
instead of the five minutes every other network call in Keelline gets. Five minutes is the right
bound for `keelline overlay create --template`, which waits on GitHub to instantiate a repository
and then clones it; it was never the right one for a diagnostic that reads one tag listing, and
`keelline init` writing a `[ci] ref` is what made that wait reachable on a freshly initialised
project.
