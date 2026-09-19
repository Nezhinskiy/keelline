Six skills join the plugin, each one a procedure an agent can be handed rather than a habit
it has to be reminded of: `file-bug` files a ledger entry a later reader can act on;
`sweep-defect-class` turns one defect into its class and closes every instance;
`review-plan-three-lenses` reviews a plan for its premises, its oracles and its trust
boundaries before the first dispatch; `attribute-failure` decides whether a failing test is
your change or your environment; `run-correctness-audit` audits a repository component by
component; and `retro-to-guard` turns a retrospective into guards, with a routing table that
gives every finding a terminal state.

`keelline test attribute --command CMD` is what `attribute-failure` runs. It takes the exact
failing command and runs it three times — the working tree as it is, `HEAD`'s committed tree
and the merge-base with your base branch, the last two extracted with `git archive` into a
scratch directory — and prints the verdict the three exit codes determine. It never moves
your checkout between commits to get its "before" reading: no `git checkout`, no `git stash`,
no `git reset`. Run 1 does execute your command in your working tree, so whatever that
command writes there it writes. The command carries its own environment sync
(`uv sync --locked && uv run pytest …`, or whatever yours is), which is what makes the tool
the same for every stack.
