`stayfixed memory index --store <overlay>/projects/<name>/memory` now resolves the same store as a
plain `stayfixed memory index` in the attached project, `developer` group included, and so writes
the same `MEMORY.md`. It used to leave the developer notes out, and `--check` then called that
index current. The same holds for every `memory` command that takes `--store`.
