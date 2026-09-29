A freshly created overlay now passes `claude plugin validate`: its marketplace names an `owner`
and both plugin manifests an `author`, which `stayfixed overlay init` sets to your account (an
existing name of your own is kept). The documentation the overlay ships in `common/memory/` is
now `_README.md`, which the note reader skips, so `memory index --check` no longer reports an
unreadable `README.md` in every attached project. `common/rules/README.md` says that nothing
reads that directory yet and that a personal standing rule is a note with `metadata.startup`,
and the overlay's README and the reference give the two `claude plugin` commands that install
the overlay.
