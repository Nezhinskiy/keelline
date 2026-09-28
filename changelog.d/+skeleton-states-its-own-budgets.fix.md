The `AGENTS.md` skeleton `stayfixed init` writes now states *your* budgets. It used to carry the
preset's three numbers as literal text — "at most 300 lines and 3,000 words, and the status
section below under 50 lines" — so a project that lowered `[budgets] agents_md_lines` to 250 was
handed a document stayfixed itself wrote saying 300 was fine, and `stayfixed docs check` then
failed that same document at line 251.

The sentence is now filled from the effective budgets: the preset's value, lowered by any
override you set (a budget may be lowered and never raised). At the preset's defaults the
rendered file is byte-for-byte what it was.
