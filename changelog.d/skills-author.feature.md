`keelline test attribute --command CMD` attributes one failing command to the change or to
the environment: it runs the command three times — the working tree as it is, `HEAD`'s
committed tree and the merge-base with the base branch, each extracted with `git archive`
into a scratch directory — and prints the verdict the three exit codes determine. It never
moves your checkout between commits to get its "before" reading — no `git checkout`, no
`git stash`, no `git reset` — though run 1 does execute your command in the working tree,
so whatever that writes there it writes. The command carries its own environment sync,
which is what makes the tool the same for every stack.

Six skills join the plugin: `file-bug` files a ledger entry a later reader can act on;
`sweep-defect-class` turns one defect into its class and closes every instance;
`review-plan-three-lenses` reviews a plan for its premises, its oracles and its trust
boundaries before the first dispatch; `attribute-failure` wraps the new `keelline test
attribute`, which runs one failing command against the working tree, `HEAD` and the
merge-base and prints a verdict; `run-correctness-audit` audits a repository by
component; `retro-to-guard` turns a retrospective into guards with a routing table that
gives every finding a terminal state.
