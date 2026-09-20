Four `keelline doctor` rows named the wrong cause.

A shipped file that is byte-for-byte what the release shipped was reported as "does not match
the release record" whenever the record was the half that was wrong — a record naming two of
three files, which `release hashes` anticipates in as many words. So did a file that was simply
absent from the installation. The three causes now have three sentences: modified, absent, and
shipped here but not in the record.

A `.keelline/local/attach.json` that is there and will not parse was reported as `skip` with
"no `git`, or a record this process could not read", and a remedy telling the owner to run
`doctor` somewhere `git` works — about a file in the checkout they are standing in. A clone can
commit that file, so it is the repository's doing: it is a `warn` now, it says the ledger cannot
be read, and the remedy names the file.

A machine configuration file that does not load was reported as `keelline.toml is here and does
not load`. `keelline doctor` reads two files and blamed the first for either, sending the owner
to fix a repository file with nothing wrong with it.
