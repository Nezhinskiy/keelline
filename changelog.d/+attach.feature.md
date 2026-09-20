`keelline attach` binds a repository to your private overlay: it checks that the overlay really
recorded this repository's remote, prints the permissions and hook entries the overlay would add,
merges them into `.claude/settings.local.json` only once you confirm, copies your Codex rules into
`.codex/rules/`, and links your notes into the checkout and every worktree — run from a linked
worktree it reaches the main checkout too, and a worktree whose directory is gone is skipped.
`keelline attach --check` reports all of that and writes nothing, and it reads the settings file
the way the real run does, so a file the run would refuse is refused by the check. Every refusal
`attach` can see coming — no `origin`, a ledger it could not have written, a `memory.groups`
entry that leaves this project's share of the overlay, a home directory the harness memory link
cannot be put under — happens before its first write.

**The path to that link is walked and never followed.** A `~/.claude` that is a symlink into a
dotfiles tree — stow, chezmoi, a synced home — is refused by name, above `attach`'s first write,
above `detach`'s first withdrawal and above the first note link a session makes in a worktree,
rather than written through: the home directory is the only thing Keelline takes on trust there,
and every component below it has to be real. A refused session therefore reports that the notes
were not linked and has linked nothing, where it used to make the note links and report that it
had not. The
refusal says which component and what to do about it. This is the same rule `keelline setup`
applies to `~/.claude/settings.json`, and the way out is the same one: make the directory real
and let your dotfiles manager adopt the files inside it.

`keelline detach` removes exactly what was added, reading a ledger it keeps under
`.keelline/local/` rather than guessing from the settings file, and leaves the binding record in
the overlay in place so a later re-attach does not re-ask. The ledger is a record and never an
authority: `.gitignore` does not untrack a committed file, so every field is held to what
`attach` could have put there, and a ledger naming anything else is refused with nothing removed.
Everything `detach` has to know before it starts — where the checkouts are, whether the
`.gitignore` region can be withdrawn — it asks before its first withdrawal, so a `git` that
cannot run or a region a merge duplicated leaves the repository untouched rather than
half-detached. `detach --json` reports counts rather than strings, because what it removes is
read out of a file a clone can commit, and the round trip is byte-for-byte: a `.gitignore` you
had before is yours after, and a directory the attach created is taken away only when it is
empty. Run `detach` from the checkout you attached from; the ledger is per-checkout.

Two refusals are worth knowing about before you meet them. `--store` must name your overlay's own
directory for this project, because the overlay root comes from your machine configuration and
never from the path you type — and the refusal states the shape of that path rather than
printing the project name, which is the repository's to choose. And a run that would grant a new
permission refuses without `--yes`: in a session driven by an agent, a step in a procedure is not
a control, so the control is the flag.

`--machine` is accepted by both commands only from an interactive shell, and refused otherwise.
It names the file that decides which overlay `attach` trusts, so it follows the rule
`KEELLINE_CONFIG` and `XDG_CONFIG_HOME` already follow: in a session nobody is sitting in front
of, the machine configuration is the one this machine records and nothing else. Omit the flag and
nothing changes.
