`keelline assess` inventories what stands between a repository and enforcement: every gate
the project configures, its own custom gates included, and what no gate runs — marker
comments, tracked `.env` files, committed notes, foreign hooks and workflows, a
CODEOWNERS file that leaves the workflows unowned or owns Keelline's workflow without the rest
of `.github/`, commit subjects outside the vocabulary,
and the configured profile's checks. The whole list goes to *.keelline/assessment.json*,
and `--json` prints the same document; the summary prints counts.
`keelline assess --builtin` runs the built-in gates and the probes and none of the commands
`[gates.custom]` names, so a clone whose commands you have not agreed to run can still be
assessed; the `init` skill uses it when you decline to run them.
When the base it compares against is not in the checkout — no `origin`, or not fetched — the
summary ends with a note saying that is why `plan`, `commit` and `bugs` could not run, and
suggests `--base refs/heads/<base_branch>` with the project's own base branch. A gate that could
not judge the tree is reported as `could not run`, never as a finding, and `assess`,
`keelline gate` and `keelline adopt promote` give each gate they ran the same `--json` row:
`name`, `enforcing`, `answered`, `reason`, `count` and `failing`.
