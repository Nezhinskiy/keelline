`keelline doctor` reports on an installation: sixteen checks covering the project's
configuration, the plugin's hook wrapper, the overlay binding and the shape of the memory path,
every hook entry with its provenance, the budgets a preset clamps, whether each injection bundle
still fits its session-start slots, the overlay's commit-time secret scan, the note store, the
last reasons a hook failed, and an environment variable that is set and quietly ignored. It
writes nothing and repairs nothing: every finding carries the command that would fix it, and
`--json` carries all sixteen. It exits 1 when any check is red and 0 otherwise — three checks
cannot be answered by this build and say so rather than guessing.

It holds a repository's bytes to the same rule as the rest of Keelline, because its `--json` is
relayed to a model. A hook entry is vouched for by the overlay this repository is bound to and
never by the ledger beside it, and is named by position rather than by its committed id; the
`diagnostics` row counts the hook sink's log and never quotes it; the `cli-path` row says that
`keelline` resolves and not where, since `PATH` reaches it from a committed `env` block; and a
file it could not read is a warning that names the file, never a red row a clone can force. It
executes only a hook wrapper it derived from its own installation — a plugin root the
environment named is read, reported and never run, and the `attached` row believes the
overlay's record over a ledger file a clone could have committed.

`doctor`'s `files` row no longer skips for want of release hashes. It compares the installed
wrapper, hook entry table and launcher against the record the release shipped beside them: a
match is green, a changed or missing file is red with the reinstall remedy, a record that is
present and unreadable is red too, and a plugin built before the record existed still skips and
says which it is. A record that names a file this build does not ship is red as well, and that
name is counted rather than printed: the record is read from the plugin root, so its keys are
text the installation's author chose and `doctor` relays no such text to a model.
