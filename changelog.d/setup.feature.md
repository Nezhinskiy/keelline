`keelline setup --preset recommended` configures a machine in one step: it writes your personal
languages and the preset name into the machine configuration file (never overwriting a value
already recorded, whether from an earlier run or your own hand), merges the preset's deny rules
and your personal values into `~/.claude/settings.json`, registers and installs the preset's
plugins on every harness that declares a marketplace for them (a missing binary or harness is a
reported note, never a failure), and tells you whether `keelline` itself is on `PATH`. Pass
`--overlay <path>` to record a private overlay you already have — validated against the
overlay's own layout and refused if it sits inside the project you ran `setup` from — or
`--overlay create:<owner>/<name> --yes` to have it create one on GitHub and record that instead;
creating one needs `--yes` (§6.1's own "after explicit confirmation"), and nothing about the
overlay happens at all unless you name `--overlay`.

`keelline setup --git-hooks` installs the commit-message hook into this repository's own hooks
directory (never `core.hooksPath`, which is global state this command has no business owning). A
hook already there is kept as `prepare-commit-msg.local` and chained to, never overwritten;
`--git-hooks --uninstall` puts it back exactly as it was.

`--home` and `--machine` point the `--preset` run at a scratch destination instead of your real
home directory and `~/.config/keelline/config.toml`, the same way every other command here takes
`--root`. They are a different destination and not a dry run: the same files are written, at the
paths you name. `--git-hooks` writes inside a repository and ignores both.
