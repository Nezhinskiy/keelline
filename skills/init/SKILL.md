---
name: init
description: Write a repository's Keelline footprint from what it can detect, or from a keelline.toml you wrote. Use when a project has no .keelline/manifest.json yet, or the user asks to initialise Keelline in it.
---

# Initialising a project

`keelline init --yes` writes a repository's footprint once: `keelline.toml` when there is
none, a `CLAUDE.md` pointer, an `AGENTS.md` skeleton where there is none and a managed section
where there is one, an ignore block, the documentation skeleton the other commands expect,
and — once a Keelline release exists to pin — a CI workflow calling the reusable gate.

The questions ship with the onboarding lane. Until then `--yes` means "take the detected
defaults", so the dry run is how the user sees them before anything is written.

## Walk

1. Show the plan first. Run `keelline init --yes --dry-run` and relay, unchanged:
   - both reports — the write-once files and the footprint are planned separately, and each
     one names every file with its verdict;
   - the CI line, which is either the release the workflow would be pinned to or one sentence
     saying why no workflow was planned;
   - the note, when there is one.
2. Ask whether to proceed. Nothing has been written at this point.
3. On a yes, run `keelline init --yes`. Add `--no-ci` instead if the user does not want a CI
   workflow and does not want the public repository asked for a pin.
4. Relay what was written and what was skipped, each with the reason the report gives. A
   skipped file is one that was already there; the run left it alone.
5. Tell the user how to undo it: `git checkout -- .` restores the files that were already
   tracked, and the files the run created have to be deleted, `.keelline/manifest.json`
   among them. There is no undo command yet — `keelline uninstall` ships later.
6. Ask the user to commit `keelline.toml`, `.keelline/manifest.json` and the footprint
   together. The manifest is what a later refresh reads to tell your edits from the tool's,
   and a footprint committed without it is a footprint nothing can maintain.
7. Offer `keelline doctor` as the next step.

## Rules

- **A `keelline.toml` the user wrote is the answer sheet, not an obstacle.** It is read for
  every key it carries — the project's name, its paths, its memory mode — and it is never
  replaced, so the paths it declares are where the footprint lands. If the user wants a value
  chosen rather than detected, have them put it in that file and run the command again.
- **A repository that already carries `.keelline/manifest.json` is refused**, and that is
  correct: refreshing a footprint is `keelline upgrade`, which ships later. Relay the refusal
  and stop; do not delete the manifest to get past it.
- **Nothing is written when anything is refused.** An exit of 1 means the report carries a
  REFUSED section, no file was touched and no manifest exists. Relay every refused line, fix
  the cause with the user, and run the command again.
- **Never hand-edit `[keelline] version`, `[keelline] state` or `.keelline/manifest.json`.**
  Those are the tool's own, and a manifest a person has altered makes every later run judge
  the wrong files.
- **A skipped CI workflow is not a failure.** Before the first Keelline release there is no
  commit to pin one to; the sentence in the report says so, and the workflow arrives later.
