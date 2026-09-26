A name holding a carriage return now comes back from git as itself. Keelline read git's answers
in text mode, which turns every `\r` into a line break, so such a name no longer matched the file
it names: a gitignored plan whose name held one was read as not ignored and written into the
committed roadmap.

`keelline docs trail` now refuses, naming the file, a specs or plans document whose name is not
UTF-8 on disk, where it used to end as `internal error: UnicodeEncodeError` and leave
`docs trail --check` stale with a remedy that crashed the same way. A carriage return in a
document's name, a theme `label` or a `[states]` value is refused like a newline: the roadmap read
back with it turned into a line break, so the listing was reported stale after every run.

Every question Keelline asks git now reads the answer the same lossless way, where six of them
still decoded it strictly and turned one byte that was not UTF-8 into an internal error: the
checkout path the hooks find their project root by (on Linux, a checkout under a latin-1
directory made every hook fail, and a hook that refuses on an internal error refused every tool
call), the `origin` URL (`init --questions` and `init --yes` crashed on one), the hooks directory
`core.hooksPath` names, the dirty-file count `test hygiene` reports, and the commit range
`commit check --range` reads, which now asks git for UTF-8 by name so a machine whose git is
configured to print another encoding no longer has plain non-ASCII messages refused. `attach`
refuses an `origin` URL that is not UTF-8 text before it writes anything, since the overlay's
record cannot hold it.

A worktree whose path holds a carriage return is listed by its own path: `setup` and `attach`
split git's listing wherever Python sees a line break, so `…/wt\rx` was taken for `…/wt`. A
checkout path that ends in a space keeps it, and a name holding a Unicode line separator is
counted once.

The output of a program Keelline launches for its exit code or a message — the command `test
attribute` runs, `gh`, `git clone`, `pre-commit`, `towncrier`, and the hook wrapper `doctor`
probes — is read with a replacement character for a byte that is not text. One such byte ended
`test attribute` as an internal error before it reached a verdict, and made `doctor`'s `wrapper`
row say only that the check could not run instead of naming the wrapper's refusal.

A memory note whose file name is not UTF-8 on disk no longer ends `keelline memory index` as an
internal error: it is set aside like a note that will not parse, and reported, because the index
names every note by its file's name. The same name no longer breaks the store's trust digest,
which made every session-start bundle and `memory trust` fail on one such committed file; a name
that is valid UTF-8 hashes as it always did, so no recorded approval changes.
