A first `stayfixed attach` now writes the store's `MEMORY.md` when there is none. The index link
it creates used to dangle, and `stayfixed memory index --check` reported the index out of date,
until `stayfixed memory index` was run.
