# Personal standing rules

Nothing reads this directory yet. It is here because the layout reserves it, and a file you put
here reaches no session.

A personal standing rule is a note in `common/memory/` that carries `metadata.startup`, the
rank it is injected at:

```
---
name: ask-before-rewriting-a-migration
description: one line saying what the rule is for
metadata:
  type: feedback
  startup: 1
---

Ask before rewriting a migration.
```

`stayfixed memory session-context --bundle standing-rules` injects every such note in full at the
start of a session, lowest `startup` first, ahead of everything that is only looked up. The rank
is what makes a rule worth a session's attention budget.

Write a rule as an instruction, not as the story of the day you learned it. "Ask before
rewriting a migration" is a rule; "remember the incident in March" is a memory. If a rule is
about one project only, it belongs in that project's `projects/<name>/memory/`, not here.
