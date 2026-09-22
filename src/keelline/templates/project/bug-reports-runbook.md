# Runbook: bug reports

How to file, close, reference and merge an entry in this project's ledger. The index links
here; the entry files are the ledger itself.

File with `keelline bugs new`; close an entry by setting its status and `fixed_in`, then run
`keelline bugs index` rather than editing the index by hand. `keelline bugs check` is the gate
over every rule the ledger holds, and `keelline bugs renumber` moves an entry and rewrites
every mention of it. The `file-bug` and `close-bug` skills walk both ends of that.
