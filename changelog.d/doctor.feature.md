`keelline doctor` reports on an installation: fifteen checks covering the project's
configuration, the plugin's hook wrapper, the overlay binding and the shape of the memory path,
every hook entry with its provenance, the budgets a preset clamps, whether each injection bundle
still fits its session-start slots, the overlay's commit-time secret scan, the note store, the
last reasons a hook failed, and an environment variable that is set and quietly ignored. It
writes nothing and repairs nothing: every finding carries the command that would fix it, and
`--json` carries all fifteen. It exits 1 when any check is red and 0 otherwise — three checks
cannot be answered by this build and say so rather than guessing.
