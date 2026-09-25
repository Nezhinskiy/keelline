A path git prints in bytes the locale cannot decode no longer turns a Keelline command into
`internal error: UnicodeDecodeError`. A non-UTF-8 filename, worktree path or branch name — an
ordinary latin-1 name on Linux — used to crash the commands that ask git about paths, among
them `attach`, `detach`, `init`, `setup` and the ledger and docs checks; git's own error text
did the same whenever it quoted such a name, and `test attribute` reported a failure over it
where it should have reached a verdict.

Keelline now reads git's answers the way Python reads the filesystem: a byte it cannot decode
is carried through unchanged rather than guessed at, so the path in the answer is the path on
disk, and a name read off the disk reaches git as its own bytes. Checks that match git's
answer against a path — whether a planned write is ignored, which plans a change touched,
which files a tracked-tree comparison expects — now answer for that path instead of failing.
The one such value Keelline writes into a file, the base branch `init` records, falls back to
`main` when its name cannot be written as UTF-8, as it does when the remote names no default
branch.
