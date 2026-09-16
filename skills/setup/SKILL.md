---
name: setup
description: Configure the machine for Keelline — the preset, the personal parameters, and the per-repository git hook. Use on a new computer, when the user asks to install Keelline's defaults, or when a commit-message hook is wanted.
---

# Machine setup

Written against the CLI contract; the command ships with the `setup` lane.

1. Run `keelline setup --preset recommended` and relay what it writes to the machine
   configuration file and which plugins and standing rules the preset enables; use
   `keelline setup --preset recommended --yes` only when the user asked for no prompts.
2. For the commit-message hook, run `keelline setup --git-hooks` inside the repository and
   relay what it installed and what existing hook it kept and chained to;
   `keelline setup --git-hooks --uninstall` restores it.
3. Personal parameters (reply language, artifact language) are the user's to set; do not
   guess them.
