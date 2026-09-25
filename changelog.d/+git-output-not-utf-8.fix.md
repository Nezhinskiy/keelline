A repository that tracks a file whose name is not UTF-8 no longer crashes Keelline. `keelline
plan check`, `bugs check` and the other commands that ask git for a list of committed paths
printed an internal error instead of an answer, because git hands such a name over as raw bytes. Git's answer is now
treated as missing — the same as when git cannot run or runs out of time — and each command says
so: `plan check` reports that nothing was linted and why, instead of blaming a shallow checkout;
`bugs check`'s reference scan and `bugs renumber`'s sweep read the files on disk instead of
quietly reading none; `test attribute` and `bugs new` name every possible cause instead of one
or two; and `attach` adds a worktree path that is not UTF-8 to what it tells you to check.

`commit check --range` now refuses a commit whose message git prints in bytes that are not UTF-8
text, instead of crashing on it. A commit can name its own text encoding, and one naming an
encoding git cannot convert from makes git print the message unconverted.
