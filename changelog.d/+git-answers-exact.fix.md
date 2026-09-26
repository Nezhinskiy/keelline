A name holding a carriage return now comes back from git as itself. Keelline read git's answers
in text mode, which turns every `\r` into a line break, so such a name no longer matched the file
it names: a gitignored plan whose name held one was read as not ignored and written into the
committed roadmap.

`keelline docs trail` now refuses, naming the file, a specs or plans document whose name is not
UTF-8 on disk, where it used to end as `internal error: UnicodeEncodeError` and leave
`docs trail --check` stale with a remedy that crashed the same way. A carriage return in a
document's name, a theme `label` or a `[states]` value is refused like a newline: the roadmap read
back with it turned into a line break, so the listing was reported stale after every run.
