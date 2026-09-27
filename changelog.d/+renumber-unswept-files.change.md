`keelline bugs renumber --json` now also lists the files it could not sweep under `unswept_files`,
each as an object with `path` and `reason`. A path may itself hold `": "`, so the existing
`unswept` strings, still printed as `"path: reason"`, could not be split back into the two
reliably. The reason no longer carries the operating system's error message verbatim, which named
an unreadable file by its absolute path: it gives the error in words, such as
`could not be read to check for BR-001 (Permission denied)`, beside the path relative to the root,
in both lists.
