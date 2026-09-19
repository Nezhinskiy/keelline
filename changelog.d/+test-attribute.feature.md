`keelline test attribute --command CMD` is a new command, and what the `attribute-failure`
skill runs. It takes the exact failing command and runs it three times — the working tree as
it is, `HEAD`'s committed tree, and the merge-base with your base branch, the last two
extracted with `git archive` into a scratch directory — and prints the verdict the three exit
codes determine. It never moves your checkout between commits to get its "before" reading: no
`git checkout`, no `git stash`, no `git reset`. Run 1 does execute your command in your
working tree, so whatever that command writes there it writes. The command carries its own
environment sync (`uv sync --locked && uv run pytest …`, or whatever yours is), which is what
makes the tool the same for every stack.
