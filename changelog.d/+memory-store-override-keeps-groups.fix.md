`stayfixed memory index --store <overlay>/projects/<name>/memory` now resolves the same store as
a plain `stayfixed memory index` in the attached project, `developer` group included, and so
writes the same `MEMORY.md`; it used to leave the developer notes out and `--check` called that
index current. The same holds for every `memory` command that takes `--store`. A first
`stayfixed attach` now writes the store's `MEMORY.md` when there is none, so the index link it
creates never dangles and `memory index --check` passes straight after. When a store does not
resolve because its overlay binding does not hold, the message now names which of the four
causes it is (no record, an unreadable record, no remote to compare, or a different remote URL)
with the way out that fits it; only a different remote URL points at `stayfixed attach
--trust-remote`. An overlay root the machine configuration records that is no longer a directory
on this machine is named as that, with `stayfixed setup --overlay` as the way out, instead of as
a project the overlay has no record of.
`stayfixed docs check --memory-graph` says when there was no store to check, and why, instead of
staying silent; its exit code is unchanged.
