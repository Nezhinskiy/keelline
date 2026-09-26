A name holding a carriage return now comes back from git as itself. Keelline read git's answers
in text mode, which turns every `\r` into a line break, so such a name no longer matched the file
it names: a gitignored plan whose name held one was read as not ignored and written into the
committed roadmap.
