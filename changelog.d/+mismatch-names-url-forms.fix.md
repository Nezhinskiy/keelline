`stayfixed attach`, `stayfixed doctor` and the memory commands no longer call a checkout "not
the repository it was bound to" when the overlay records a different remote URL. Remote URLs are
compared exactly, so the same repository cloned over https where the overlay recorded ssh (or the
other way round) is refused as a mismatch too; the message now says a different remote URL was
recorded and that another URL form of the same repository counts, and `--trust-remote` still
rebinds it.
