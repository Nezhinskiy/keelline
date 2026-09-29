A freshly created overlay now passes `claude plugin validate`: its marketplace names an `owner`
and both plugin manifests an `author`, which `stayfixed overlay init` sets to your account (an
existing name of your own is kept). The documentation the overlay ships in `common/memory/` is
now `_README.md`, which the note reader skips, and `stayfixed overlay upgrade` removes the old
`README.md` where it still holds the text 0.1.x shipped, so after an upgrade `memory index
--check` no longer reports it unreadable in every attached project; a copy you edited is kept,
and the report says to rename it to `_README.md`. `common/rules/README.md` says that nothing
reads that directory yet and that a personal standing rule is a note with `metadata.startup`,
and the overlay's README and the reference give the two `claude plugin` commands that install
the overlay.
