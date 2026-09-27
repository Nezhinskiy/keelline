A `keelline.toml` can no longer put its own bytes into the terminal through an unknown key. TOML
keys are arbitrary quoted text, and the two refusals that report one — `[<table>] has unknown
key(s)` and `[budgets] has unknown key(s)` — joined them in raw, so a committed configuration
could send escape sequences and newlines to your terminal and into a refusal the `init` skill
relays to a model. It was reachable on every table.

Both now follow the rule the unknown-*section* refusal already followed: a plain name is named,
so a typo is still worth reading, and anything else is counted and never quoted. The
missing-key message beside them is unchanged — it is built from Keelline's own schema names.
