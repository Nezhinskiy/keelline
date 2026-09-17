---
name: setup
description: Configure the machine for Keelline — the preset, the personal parameters, and the per-repository git hook. Use on a new computer, when the user asks to install Keelline's defaults, or when a commit-message hook is wanted.
---

# Machine setup

`keelline setup` is written against the CLI contract and ships with the `setup` lane; it is
not available yet. If it is rejected as an unknown command, say so and stop — do not
improvise a substitute. The `keelline overlay` commands in step 4 have shipped.

1. Run `keelline setup --preset recommended` and relay what it writes to the machine
   configuration file and which plugins and standing rules the preset enables; use
   `keelline setup --preset recommended --yes` only when the user asked for no prompts.
2. For the commit-message hook, run `keelline setup --git-hooks` inside the repository and
   relay what it installed and what existing hook it kept and chained to;
   `keelline setup --git-hooks --uninstall` restores it.
3. Personal parameters (reply language, artifact language) are the user's to set; do not
   guess them.
4. Offer the private overlay — one repository holding the user's own standing rules,
   cross-project notes and per-project bindings. Creating one on their account needs their
   word first, so ask before running
   `keelline overlay create --owner NAME --name keelline-private --template`. To render one on
   the machine with no network call, run `keelline overlay create --owner NAME --local`
   instead. Then run `keelline overlay init --owner NAME --root PATH`, and relay what it
   renamed and whether the secret scan installed.
5. After a Keelline release, `keelline overlay upgrade --root PATH --dry-run` says what would
   change. Relay the report, and relay the `ASK FIRST` list separately: those two files can
   grant a capability, so the user agrees to them by name before the run without `--dry-run`.
