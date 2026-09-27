Keelline no longer writes anything inside a repository's `.git/`. Nothing reserved it: a
`keelline.toml` could point any `[paths]` key at `.git/hooks/pre-commit` and `keelline init`
would rewrite that hook in place, keeping its executable mode, or create a file of the clone's
choosing anywhere else in git's control directory.

A path whose components include `.git` is now refused before anything is written — at any depth,
so a submodule's control directory is covered too, and whatever the case, because `.GIT/` reaches
the same directory on a case-insensitive filesystem. The refusal names the key and never quotes
the value. The rule is `.git` specifically and not "a leading dot": `.github/workflows/`,
`.keelline/`, `.gitignore` and `.gitattributes` are unaffected.

`keelline setup --git-hooks` still installs Keelline's own commit-message hook. It asks git
where the hooks directory is rather than taking a path from the repository, which is why it is
not what this refuses.
