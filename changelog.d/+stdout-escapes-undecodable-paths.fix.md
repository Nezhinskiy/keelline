A command whose summary names a path that is not UTF-8 no longer ends as `internal error:
UnicodeEncodeError` with exit 2 under a UTF-8 locale such as `en_US.UTF-8`. Such a path is printed
with each byte it could not decode escaped (`caf\udce9.md`), and the command's own exit code
stands. Every other output is unchanged: `--json` and hook output already escape every non-ASCII
character, and where Python writes undecodable bytes back as they were (its UTF-8 mode, with
`LANG` unset), they still are.
