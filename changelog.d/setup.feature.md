`keelline setup --preset recommended` configures a machine in one step: it writes your personal
languages and the preset name into the machine configuration file, merges the preset's deny rules
and your personal values into `~/.claude/settings.json`, registers and installs the preset's
plugins on every harness that declares a marketplace for them (a missing binary or harness is a
reported note, never a failure), and tells you whether `keelline` itself is on `PATH`. Pass
`--overlay <path>` to record a private overlay you already have, or
`--overlay create:<owner>/<name> --yes` to have it create one on GitHub and record that instead;
creating one needs `--yes`, because it is the one irreversible, outward-facing act this command
performs — `--yes` confirms nothing else, since nothing else asks — and nothing about the overlay
happens at all unless you name `--overlay`.

Everything `setup` can refuse, it refuses before its first write. An `--overlay` path must be a
real overlay — both `.claude-plugin/` manifests naming it `keelline-overlay[-<owner>]` and
`keelline-overlay-marketplace[-<owner>]`, not merely present — and must lie outside the
repository `--root` names: not inside it, not above it, and not in another checkout of it, since
a worktree is not a different repository and a clone ships its tree into all of them. For
`create:`, the destination is known from the arguments and refused before `gh repo create` runs;
the one check that cannot precede the call, a template that generated something that is not an
overlay, says that the repository now exists and where. A mistyped `--preset` is refused before
the home directory is created for it.

The machine configuration file is shared with you and is merged, table by table and key by key,
on every run: a value already recorded — by an earlier run or your own hand — is never
overwritten by a preset default, an `[overlay]` key you wrote survives a run that only changed
your languages, and a table `setup` knows nothing about is carried through. Values the standard
library can parse round-trip; a shape TOML cannot spell is refused naming the file and the key.
Comments do not survive, because the file is parsed and rewritten. The `[personal]` values are
mirrored into `pluginConfigs` in `~/.claude/settings.json` and recomputed from the machine file
on every run. A home directory managed by stow, chezmoi or a synced folder is refused naming the
link and a `--home` that writes the real file, not reported as an internal error.

`keelline setup --git-hooks` installs the commit-message hook into this repository's own hooks
directory (never `core.hooksPath`, which is global state this command has no business owning). A
hook already there is kept as `prepare-commit-msg.local` and chained to, never overwritten;
`--git-hooks --uninstall` puts it back exactly as it was.

`--home` and `--machine` point the `--preset` run at a scratch destination instead of your real
home directory and `~/.config/keelline/config.toml`, the same way every other command here takes
`--root`. They are a different destination and not a dry run: the same files are written, at the
paths you name. `--machine` defaults to the file every reader reads, never to one
`XDG_CONFIG_HOME` chose. `--git-hooks` writes inside a repository and ignores both.
