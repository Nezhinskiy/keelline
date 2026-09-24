---
name: uninstall
description: Remove Keelline's footprint from a repository, leaving hand-edited files in place and listed. Use when the user asks to uninstall or remove Keelline from a project.
---

# Uninstalling

`keelline uninstall` removes every file Keelline wrote whose bytes are still the ones it wrote,
takes its sections out of files that hold other text, and removes its ledger. A file the user
edited stays where it is and is listed.

1. If the repository is attached to an overlay, run `keelline detach` first. `uninstall`
   refuses otherwise, and says so.
2. Run `keelline uninstall --dry-run` and relay both reports and every `note:` line. The note
   about `AGENTS.md` means the real run judges the skeleton after taking Keelline's section
   out, so a file the dry run calls edited there may still go.
3. A `note:` counting files under `.keelline/local/` means the real run will refuse. They are
   the user's notes kept out of git, or an edited file kept out of git, and the ignore block
   this command removes is what keeps them out of it. Relay the count. Moving them is the
   user's decision; never move or delete them yourself.
4. For each file left in place, ask the user. Add `--force <path>` only for a file they name,
   with the path exactly as the report prints it. Forcing `AGENTS.md` takes Keelline's section
   out of it, never the rest of the file.
5. If any `--force` was added, run `keelline uninstall --dry-run` again with the same flags and
   relay the new reports before anything is removed.
6. Run `keelline uninstall` with the same flags, and relay both reports and the count of files
   left in place.

## Rules

- **An exit of 1 removed nothing.** A `REFUSED` section names each artifact and why. Relay it
  and stop.
- **An exit of 2 is a refusal, and it may have come part-way through.** Attached, files kept
  under `.keelline/local/` counted before the run, and a `--force` path outside the root come
  before anything is removed. A file that cannot be removed, or files still under
  `.keelline/local/` after the write-once pass, stop the run part-way: what was removed stays
  removed, and the ignore block and the manifest stay so the next run can finish. Relay it as
  printed, run `git status` to show the user what changed, and after they deal with the cause run
  `keelline uninstall --dry-run` again.
- **A target printed as `<id>` is one the manifest recorded outside the path grammar.** Relay it
  as printed, and never look up or guess the path behind it.
