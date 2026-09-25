Keelline no longer crashes on a repository that tracks a file whose name is not UTF-8. `keelline
plan check`, `bugs check`, `bugs renumber` and the other commands that ask git for committed
paths stopped with an internal error, because git hands such a name over as raw bytes. Each now
treats it as git giving no usable answer, like a git that cannot run or runs out of time, and
says so: `plan check` reports that nothing was linted and why; `bugs check` and `bugs renumber`
read the files on disk instead; `bugs new` still counts the entries other branches hold, and
warns when it could not read that history rather than handing out a number one of them may
already use; `test attribute`, `bugs new` and `attach` name every cause they could have met.

`commit check --range` now refuses a commit whose message git prints in bytes that are not UTF-8
text, instead of crashing on it. A commit can name its own text encoding, and one naming an
encoding git cannot convert from makes git print the message unconverted.
