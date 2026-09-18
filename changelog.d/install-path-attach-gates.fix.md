`keelline attach`, `keelline detach` and the two `keelline doctor` rows that read what they leave
behind now hold a repository's own bytes to the same rule as the rest of Keelline, and stop
treating a gate asked once as a gate.

**`attach` refuses a checkout with no `origin` before it writes anything.** That refusal used to
happen after the `.gitignore` region, the `.codex/rules/` copies, the settings merge and the
ledger were all on disk — so the command exited `2` having changed four things, and `keelline
doctor` then reported the repository attached, because it keys on the ledger existing. All four
of `attach`'s refusals now happen before its first write.

That applies to the ledger too: an existing `.keelline/local/attach.json` is read and validated
before the first write, so a committed one that `attach` could not have produced stops the run
rather than being discovered four writes in. And to `memory.groups`: an entry that leaves this
project's share of the overlay was refused by the write that created the directory, which is five
artifacts into the run — including the overlay's binding record, which is what made `keelline
doctor` call such a repository not merely attached but *bound*. It is now refused before the
first write, like every other cause of exit `2` that `attach` can see coming.

**`detach` treats `.keelline/local/attach.json` as a record and no longer as an authority.**
`.gitignore` does not untrack a file a clone committed, so that path can arrive in a fresh
checkout with contents nobody on your machine wrote — and `detach` deleted files by the strings
in `rules` and dropped settings keys by the strings in `settings_keys`. A ledger claiming
`settings_keys = ["permissions"]` deleted your whole `permissions` block, **deny rules
included**. Every field is now held to what `attach` could have put there — a single file under
`.codex/rules/`, and the one `autoMemoryDirectory` key — and a ledger naming anything else is
refused (`2`) with nothing removed.

**`detach --json` reports counts rather than strings**, for the same reason `attach --check`
already reports a count of the rules it found already present: everything `detach` removes is
read out of a file a clone can commit, and that output is relayed to a model.

**The `autoMemoryDirectory` fallback is withdrawn when its reason goes.** It is taken only when
the harness memory symlink cannot be made; once the symlink can be made, or once the store's
trust record lapses, the setting is now removed in the same run — and what the ledger records is
read back from the settings file rather than remembered from the run that wrote it, so a second
attach can no longer forget a key it left behind. A `git pull` that lapsed your trust record used
to close every channel except this one.

**`attach` and `detach` run from a linked worktree reach the main checkout.** They applied the
owning-checkout entry point to whatever `--root` named and then skipped the owner, so attaching
from a worktree left the main checkout with no note links at all — silently, exit `0`.

**Withdrawing the link tree no longer removes a symlink Keelline did not create.** A group name
in `paths.memory` pointed at a directory of your own was deleted by `detach` and reported as
revoked; only a link whose target is this project's own share of the overlay is withdrawn now.

**A hook entry is vouched for by the overlay, not by the ledger beside it.** `keelline doctor`
reported "all accounted for" when a repository committed a marked hook entry *and* an attach
ledger recording that entry's id — a committable file silencing the one check whose purpose is
that nobody's entries go unlisted. An entry claiming the Keelline marker is now accounted for
only if the overlay this repository is bound to still grants that exact command; where the
overlay cannot be asked, the row says so rather than absolving anything. If you edit the overlay
and do not re-attach, this row will name the entries that have drifted and tell you to run
`keelline attach`, which takes them out.

**Two `doctor` rows stop being wrong in the reader's favour.** The `attached` row compares the
harness memory path against the store instead of printing "a link to the store" for any symlink
at all: a dangling link, or one pointing at an unrelated directory, is now red and says which,
and a path that is simply absent is green only while your trust record is what is keeping it
absent. And a file Keelline could not read is a warning that names it rather than a red row
saying "this check could not run" — a committed ledger could force `hook-entries` red and exit
`1` on a healthy installation, and an unreadable `${CLAUDE_PLUGIN_DATA}` did the same to
`diagnostics`.

One thing `attach` now takes away rather than adds: when withdrawing the `autoMemoryDirectory`
fallback empties `.claude/settings.local.json`, the file itself is removed, because `{}` is not
what that file looked like before `attach` created it. It can only happen when Keelline's own key
was the file's entire contents.

`keelline detach` asks `git` where this repository's checkouts are *before* it withdraws
anything, rather than between the settings file and the link trees. On a machine where `git`
cannot run, it used to exit `1` with your `.claude/settings.local.json` rules and your
`.codex/rules/` files already removed and every note link still in place; now it stops with
nothing touched.

And one limitation worth knowing rather than discovering: `keelline detach` reads the ledger from
the checkout it is run from, and `.keelline/local/` is untracked and per-checkout. Run it from the
checkout you attached from; once it starts, it reaches every checkout of the repository.
