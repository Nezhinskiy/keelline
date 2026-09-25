`keelline assess` inventories what stands between a repository and enforcement: every gate
the project configures, its own custom gates included, and what no gate runs — marker
comments, tracked `.env` files, committed notes, foreign hooks and workflows, a
CODEOWNERS file that leaves the workflows unowned, commit subjects outside the vocabulary,
and the configured profile's checks. The whole list goes to *.keelline/assessment.json*,
and `--json` prints the same document; the summary prints counts.
