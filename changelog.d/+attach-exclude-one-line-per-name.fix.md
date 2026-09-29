`stayfixed attach` no longer lets a memory group's name write more than one line into the
repository's exclude file. A name holding U+2028, a NUL, a form feed or another character some
line reader splits at is now left visible in `git status` instead of being listed, and the block
an earlier attach wrote is read back one line per line git sees. Before, a second attach could
split such a name into separate lines, one of which could un-hide a file your own excludes
file hides (such as `.env`) or hide unrelated files.
