On macOS under a locale that is not UTF-8 (for example `LC_ALL=en_US.ISO8859-1`), Keelline no
longer misreads a file name with non-ASCII characters in git's answers. It used to read git's
output, and write names to git, in the locale's encoding while the file system names them in
UTF-8, so a name such as `café.md` never matched: among other things `docs trail` could list a
gitignored document in the committed roadmap. Git is now spoken to in the file system's own
encoding, the one every path on the machine uses.
