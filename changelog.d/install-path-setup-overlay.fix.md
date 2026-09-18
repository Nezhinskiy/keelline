`keelline setup` and the `keelline overlay` commands now refuse what they cannot do *before* they
do anything else, and the machine configuration file survives being shared with a human.

**`keelline setup --overlay create:<owner>/<name>` no longer creates the repository first and
refuses afterwards.** Run from your home directory — where `--root` defaults to `.` — the
documented command created the private repository on GitHub, cloned it, renamed its manifests and
installed the secret scan, and only then refused, because the overlay would have landed inside
the "project" that `--root` had defaulted to. Nothing in the refusal said the repository now
existed. The destination is known from the arguments, so it is checked first; and in the one case
that cannot be checked first — a template repository generated something that is not an overlay —
the refusal says the repository was created, and where.

**`keelline setup --overlay <path>` is validated before the first write too.** A mistyped path
used to leave the machine file written, `~/.claude/settings.json` merged and two plugins
installed, and then exit `2` reporting only the typo.

**What counts as an overlay is now one question with one answer.** Both `.claude-plugin/`
manifests must *name* the tree `keelline-overlay[-<owner>]` and
`keelline-overlay-marketplace[-<owner>]` — the names `overlay create` renders and `overlay init`
writes — rather than merely existing, which any Claude Code plugin repository satisfies. And the
overlay root must lie outside the repository `--root` names: not inside it, not above it, and not
in another checkout of it. A worktree is not a different repository, and that gap was reachable
with `--root` set to one, which is this project's own default way of working.

**`keelline overlay upgrade` checks that `--root` is an overlay.** `--root` defaults to `.`, and
in a directory that was not an overlay the command created the overlay's fourteen missing files —
both plugin manifests, `hooks/hooks.json`, `.gitignore` and `.github/workflows/scan.yml` among
them — reported them as work done and exited `0`.

**`keelline overlay create --template` says what actually went wrong.** With `gh` not installed,
it launched three subprocesses and then blamed your GitHub authentication. It now reports `gh`'s
own exit code and message, stops after the first call when `gh` could not be launched at all, and
names the precondition `--template` really has today: nothing publishes the template repository
yet, so `--local` is the source that works.

**`keelline overlay init` names the Codex manifest too**, so the collision the owner suffix exists
to prevent stops happening on Codex, and it re-stamps what it rewrites into
`.keelline/manifest.json` — without which both manifests read as hand-edited from that moment on,
and no release could refresh the file carrying the version-compatibility declaration.

**A symlink between your home directory and `.claude/settings.json` is a refusal with a remedy
that works.** A home managed by stow, chezmoi or a synced directory aborted `keelline setup` with
`internal error: UnsafePath`, after the machine file had been written. The refusal now names the
link, where it leads, and a `--home` that really writes the file the link leads to — and where no
`--home` can express the layout, it says so rather than printing a command. `stow` linking the
file rather than the directory (`~/.claude/settings.json -> <dotfiles>/claude/settings.json`) is
that case, since `--home H` writes `H/.claude/settings.json` and nothing else: point the link at
a path ending in `.claude/settings.json`, or let `keelline setup` write a real file and have your
dotfiles manager adopt it.

**The machine configuration file is no longer flattened by the command that shares it.**
`keelline setup` kept three tables and replaced the rest, so a `[trust]` table or a key you wrote
at the top level was gone after one run; every table is now carried through. A value the
serialiser could not write — `scale = 1.5`, or a `[personal.editor]` sub-table — used to make
*every* future run exit `2` naming a serialiser you have never heard of; those round-trip now, and
what is left refusable names the file and what to do about it. Comments still do not survive a
rewrite: the file is parsed and written back, and nothing in the standard library keeps them.

**`keelline setup --machine` defaults to `~/.config/keelline/config.toml`**, the file every reader
reads. It used to fall back to the same interactive sniff `attach` uses, so with
`XDG_CONFIG_HOME` set you could write a machine file, exit `0`, and have every reader — and
`keelline doctor` — report that there was none. `keelline setup --help` also stops printing the
home directory of whoever built the parser.

**The `[personal]` values mirrored into `pluginConfigs` follow the machine file.** The mirror was
written once and never again, so editing `reply_language` in the machine file — the documented way
— left `""` in `~/.claude/settings.json` for ever. It is recomputed on every run; the machine file
is the copy that wins.
