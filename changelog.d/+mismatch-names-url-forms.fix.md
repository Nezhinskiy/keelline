`stayfixed attach` and `stayfixed doctor` no longer call a checkout "not the repository it was
bound to" when the overlay records a different remote URL. URLs are compared exactly, so an https
clone of a repository the overlay recorded over ssh (or the other way round) is a mismatch too,
and the message now says so; `--trust-remote` still rebinds it. A checkout with no `origin` is no
longer a mismatch at all: `attach`, `attach --check` and `doctor` called it one and pointed at
`--trust-remote`, which then refused for the missing `origin`. The memory commands used to answer
every binding failure with one sentence, that the overlay does not record this repository's origin
remote for the project, and to run `stayfixed attach`. They now name the cause (no `origin` in this
checkout, no remote recorded for the project, an unreadable record, a different remote URL, or an
overlay root that is no longer a directory on this machine) with the way out that fits it, only a
different remote URL points at `--trust-remote`, and a missing `origin` is said in the same words
by the memory commands, `attach`, `attach --check`, `doctor` and the session-start line.
