# Starting the adoption

After the footprint is written:

1. If `init` printed a `note: keelline.toml configures … custom gate(s)` line, the file the user
   kept names commands of its own, and `keelline assess` runs them. Name those gates to the
   user, say that the next command runs their commands on this machine, and ask for an explicit
   yes. **Silence, a timeout or an empty answer is a no.** On a no, stop here: the footprint is
   written and nothing ran. Then run `keelline assess` and relay the summary: its table of
   gates, and its table of items when there are any. The whole list is in
   `.keelline/assessment.json`. Use it for the next step, and never paste it wholesale.
2. Brainstorm the adoption with the user, through a brainstorming skill if the harness has
   one, otherwise one question at a time:
   - which gates the project runs: the built-in ones it keeps, and any command of its own
     added as a custom gate under `[gates]` in `keelline.toml`;
   - which gates to enforce first;
   - which findings to fix, and which to file as ledger entries through the `file-bug` skill;
   - what the project deliberately does differently.
3. Put the design in the `[paths] specs` directory as `<date>-keelline-adoption-design.md` and
   the plan directly in `[paths] plans`, not a subdirectory, as `<date>-keelline-adoption.md`.
   The word `keelline`, as one of the hyphen-separated words of the file name, is how the
   adoption commands recognise the plan. A second adoption, such as a subproject's, adds a slug:
   `<date>-keelline-adoption-<slug>.md`. Give the plan the `**Scope:**` line
   `keelline plan check` requires, and a `**Premise:**` line if it claims to fix a ledger
   entry. Run `keelline plan check <plan>` until it passes.
4. Bring the roadmap's trail up to date, or the `trail` gate fails the next check. In the
   `trail.toml` beside the roadmap, under `[states]`, give both documents a state — the key is
   the listing's row, the last segment of `[paths] specs` or `plans`, a slash and the file name
   (`specs/<file>`, not `docs/specs/<file>`), the value one line such as `in progress`:
   unset, a new document is listed `delivered`, and the adoption command refuses the plan.
   Stage both documents (the listing reads only
   tracked files), run `keelline docs trail`, then `keelline docs trail --check`.
5. Show the user the plan's path, and say that the next command rewrites Keelline's own keys
   in `keelline.toml`. Ask for an explicit yes. **Silence, a timeout or an empty answer is a
   no.** On a yes, run `keelline adopt begin <plan>`.
6. End with one message saying:
   - what was written, and what was skipped and why;
   - how many findings the plan covers;
   - the next command, `keelline adopt promote`, which enforces every gate that passes now and
     names the rest; run it again as the plan lands;
   - the undo: `keelline uninstall`.

Ask the user to commit `keelline.toml`, `.keelline/manifest.json`, the footprint, the design,
the plan, `trail.toml` and the roadmap together.
