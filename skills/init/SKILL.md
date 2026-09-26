---
name: init
description: Take a repository onto Keelline — show what it detected, ask the questions a person may answer, write the footprint, assess the repository, and start its adoption. Use when a project has no .keelline/manifest.json yet, or the user asks to initialise Keelline in it.
---

# Initialising a project

Ask through the harness's ask-the-user tool when it has one, and one plain question per turn
when it does not; [references/asking.md](references/asking.md) fits each step to the
harness's limits. Never run this skill in a forked context: a subagent cannot ask.

## Walk

1. Run `keelline init --questions --json`. It refuses a repository that already has
   `.keelline/manifest.json` (offer `keelline upgrade`) or a `keelline.toml` (see the first
   rule). Otherwise `questions.properties` holds six questions, each with its `default` (what
   `keelline init --yes` alone would write), its `x-keelline-source` and its `x-keelline-flag`.
2. Show the first four defaults (name, base branch, agents, profile), each with its source, as
   **one** confirm question. A name with no default is "not derivable": ask for it. On a "no",
   ask which values are wrong, then ask only those.
3. Ask `memory.mode`. If the user picks the overlay and its option says the setup skill
   creates one next, ask one follow-up: set one up now, or keep notes on this machine until
   then, which is the answer `local-only`.
4. Ask whether to keep any of the files in `artifacts.local` out of git, with no as the
   default. Only on a yes, ask which. Most projects keep none.
5. Build the command: `--yes --dry-run`, then each answer that differs from its default as its
   `x-keelline-flag`, once per item for a list, such as
   `keelline init --yes --dry-run --name widget --local roadmap-history`. Run it and relay both
   reports, the `CI:` line and every `note:` line. Ask for a final yes. **Silence, a timeout or
   an empty answer is a no.**
6. On a yes, run the same command without `--dry-run`, and relay the real run the same way.
   Add `--no-ci` to both if the user wants no CI workflow and no remote asked for a pin.
7. If the answer was the overlay: when the machine records none, hand over to the `setup`
   skill to create or record one; then hand over to the `attach` skill to bind this
   repository. Each asks its own confirmations. Come back here afterwards.
8. Start the adoption: [references/adoption.md](references/adoption.md).

## Rules

- **A `keelline.toml` the user wrote answers the questions.** Skip steps 2–4 and run steps 5
  and 6 with no answer flag: the dry run, the relay, the explicit final yes, then the write. The
  file is kept; a missing `[keelline] version` is the one thing added, and a `note:` line says so.
- **A `failed:` line from `init` over a `keelline.toml` the user wrote means the next command
  could not load that file.** Nothing was written. Relay the sentence, fix the file with the
  user, and run again.
- **A repository with `.keelline/manifest.json` is refused.** Refreshing is `keelline upgrade`.
  Never delete the manifest to get past it.
- **Nothing is written when anything is refused.** Relay every `REFUSED` line, fix the cause
  with the user, and run again.
- **A `CI:` line saying the workflow was skipped is the whole answer about CI.** Before the
  first Keelline release there is no commit to pin, and the sentence says so.
- **Never hand-edit `[keelline] version`, `state`, `enforced`, `[ci] ref` or
  `.keelline/manifest.json`.** They are the tool's: the adoption commands move `state` and
  `enforced`, and `keelline upgrade` moves the version and the ref.
- **The undo is `keelline uninstall`.** Run `keelline uninstall --dry-run` first.
