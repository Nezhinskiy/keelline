---
name: init
description: Set up Keelline in a repository — questions, footprint, then an assessment and an adoption plan. Use when a project has no keelline.toml yet, or the user asks to install, initialise or adopt Keelline.
---

# Initialising a project

Written against the CLI contract; the command ships with the `onboarding` lane and is not
available yet. If an invocation below is rejected as an unknown command, say so and
stop — do not improvise a substitute.

1. Show what would be written first: run `keelline init --dry-run` and relay the list of
   files, managed regions and settings entries it names, unchanged.
2. The command asks three questions (project name, base branch, preset). If the user has
   already answered them, write the answers to a file and run `keelline init --answers FILE`;
   to accept every default, run `keelline init --yes`.
3. Relay the final message as printed: what was written, what was skipped and why, how many
   findings the adoption plan covers, the next command, and the undo command.
4. Do not edit `keelline.toml`'s tool-owned keys or `.keelline/manifest.json` by hand.
