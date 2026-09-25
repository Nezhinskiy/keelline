A path git prints in bytes that are not UTF-8 no longer turns a Keelline command into
`internal error: UnicodeDecodeError`. A non-UTF-8 filename, worktree path or branch name — an
ordinary latin-1 name on Linux — used to crash the commands that ask git about paths, among them
`plan check`, `bugs check`, `bugs renumber`, `attach`, `detach`, `init` and `setup`; git's own
error text did the same whenever it quoted such a name, and `test attribute` reported a failure
over it where it should have reached a verdict.

Keelline now reads git's answers the way Python reads the filesystem: a byte it cannot decode is
carried through unchanged rather than guessed at, so the path in the answer is the path on disk,
and a name read off the disk reaches git as its own bytes. Checks that match git's answer against
a path — which plans a change touched, whether a document is ignored, which files a tracked-tree
comparison expects, whether an overlay root is another checkout of the project — answer for that
path instead of failing. `keelline gate` refuses a base whose `keelline.toml` is not UTF-8 text,
in the words it uses for the tree's own copy, rather than reading it.

When git gives no answer at all — it cannot run or runs past its time limit — each command says
so instead of reading it as "nothing": `plan check` reports that nothing was linted and why, rather
than blaming a shallow checkout; `bugs check` and `bugs renumber` read the files on disk instead;
`bugs new` still counts the entries other branches hold, and warns when it could not read that
history rather than handing out a number one of them may already use; and `test attribute`,
`bugs new` and `attach` name every cause they could have met.

`commit check --range` now refuses a commit whose message git prints in bytes that are not UTF-8
text, instead of crashing on it. A commit can name its own text encoding, and one naming an
encoding git cannot convert from makes git print the message unconverted.
