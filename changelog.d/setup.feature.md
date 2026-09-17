`keelline setup --preset recommended` configures a machine in one step: it writes your personal
languages and the preset name into the machine configuration file, merges the preset's deny
rules and your personal values into `~/.claude/settings.json`, installs the preset's plugins into
every harness you have (a missing one is a reported note, never a failure), and tells you whether
`keelline` itself is on `PATH`. Pass `--overlay <path>` to record a private overlay you already
have, or `--overlay create:<owner>/<name>` to have it create one on GitHub and record that
instead — nothing about the overlay happens unless you name that answer, `--yes` included.

`keelline setup --git-hooks` installs the commit-message hook into this repository's own hooks
directory (never `core.hooksPath`, which is global state this command has no business owning). A
hook already there is kept as `prepare-commit-msg.local` and chained to, never overwritten;
`--git-hooks --uninstall` puts it back exactly as it was.

`--home` and `--machine` let you point either command at a scratch location instead of your real
one, the same way every other command here takes `--root`.
