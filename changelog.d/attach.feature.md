`keelline attach` binds a repository to your private overlay: it checks that the overlay really
recorded this repository's remote, prints the permissions and hook entries the overlay would add,
merges them into `.claude/settings.local.json` only once you confirm, copies your Codex rules into
`.codex/rules/`, and links your notes into the checkout and every worktree. `keelline attach
--check` reports all of that and writes nothing. `keelline detach` removes exactly what was added,
reading a ledger it keeps under `.keelline/local/` rather than guessing from the settings file,
and leaves the binding record in the overlay in place so a later re-attach does not re-ask.

Two refusals are worth knowing about before you meet them. `--store` must name your overlay's own
directory for this project, because the overlay root comes from your machine configuration and
never from the path you type. And a run that would grant a new permission refuses without `--yes`:
in a session driven by an agent, a step in a procedure is not a control, so the control is the
flag.
