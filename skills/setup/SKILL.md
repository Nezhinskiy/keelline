---
name: setup
description: Configure the machine for Keelline — the preset, the personal parameters, and the per-repository git hook. Use on a new computer, when the user asks to install Keelline's defaults, or when a commit-message hook is wanted.
---

# Machine setup

1. Run `keelline setup --preset recommended` and relay what it writes to the machine
   configuration file and which plugins and standing rules the preset enables. It asks nothing;
   `--yes` exists only to confirm creating an overlay repository (step 4).
2. For the commit-message hook, run `keelline setup --git-hooks` inside the repository and
   relay what it installed and what existing hook it kept and chained to;
   `keelline setup --git-hooks --uninstall` restores it.
3. Personal parameters (reply language, artifact language) are the user's to set; do not
   guess them.
4. Offer the private overlay — one repository holding the user's own standing rules,
   cross-project notes and per-project bindings. `setup` is what records it, through
   `--overlay`, and there are two ways in:
   - **They already have one**: `keelline setup --preset recommended --overlay /path/to/it`.
     The path is validated against the overlay's own layout and refused if it sits inside the
     project `setup` was run from.
   - **They do not**: `keelline setup --preset recommended --overlay create:<owner>/keelline-private --yes`
     creates it on their GitHub account and records it in one step. Creating a repository on
     their account needs their word first, so **ask before running it** — `--yes` is that
     consent and nothing about the overlay happens unless `--overlay` is named at all.

   The lower-level path still exists and is for two cases only — an overlay rendered without
   recording it, or one somebody else created that needs renaming:
   `keelline overlay create --owner NAME --local` renders one on this machine with no network
   call, `keelline overlay create --owner NAME --name keelline-private --template` creates it on
   GitHub once the template repository is published to their account, and `keelline overlay
   init --owner NAME --root PATH` makes it theirs. Relay what
   `init` renamed and whether the secret scan installed.
5. After a Keelline release, `keelline overlay upgrade --root PATH --dry-run` says what would
   change. Relay the report, and relay the `ASK FIRST` list separately: those two files can
   grant a capability, so the user agrees to them by name before the run without `--dry-run`.
6. **The preset's plugins install on Claude Code only.** Codex has no verified non-interactive
   marketplace source for them, so `setup` reports the gap as a note rather than attempting an
   unverified install. Relay that note and tell the user to add those plugins by hand on Codex;
   do not present the run as having configured both harnesses.
7. `--home` and `--machine` point the `--preset` run at a scratch destination instead of the
   real home directory and `~/.config/keelline/config.toml`. They are **not** a dry run — the
   same files are written, just elsewhere — and `--git-hooks` ignores both. Do not offer them
   as a way to preview what `setup` would do; there is no such mode.
