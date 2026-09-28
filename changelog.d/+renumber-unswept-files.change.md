`stayfixed bugs renumber --json` now lists each file it could not sweep under `unswept` as an object
with `path` and `reason`, where it was a `"path: reason"` string: a path may itself hold `": "`, so
such a string could not be split back into the two reliably. The reason no longer carries the
operating system's error message verbatim, which named an unreadable file by its absolute path: it
gives the error in words, such as `could not be read to check for BR-001 (Permission denied)`,
beside the path relative to the root.
