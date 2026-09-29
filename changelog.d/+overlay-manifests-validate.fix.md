A freshly created overlay now passes `claude plugin validate`: its marketplace names an `owner`
and both plugin manifests an `author`, which `stayfixed overlay init` sets to your account (an
existing name of your own is kept). The documentation the overlay ships in `common/memory/` is
now `_README.md`, which the note reader skips. `stayfixed overlay init` and `stayfixed overlay
upgrade` remove the old `README.md` where it still holds the text 0.1.x shipped, so `memory index
--check` no longer reports it unreadable in every attached project; a copy you edited is kept, and
the line says to rename it to `_README.md`.
