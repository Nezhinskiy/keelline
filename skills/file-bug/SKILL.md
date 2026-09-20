---
name: file-bug
description: File a bug-ledger entry that a later reader can act on — the reproduction, the evidence and its boundary, and a suggested fix marked as the hypothesis it is. Use when a defect is found and is not being fixed in the same change.
---

# Filing a ledger entry

1. Reproduce before writing. Run the failing thing and keep the raw output; an entry whose
   "before" nobody observed is an entry nobody can trust.
2. Allocate the entry: `keelline bugs new "one sentence naming the defect" --severity high --area cli`.
   Severity is what the defect costs, not how hard the fix is; `--area` is the area of
   `src/` it lives in. The command writes the entry skeleton and regenerates the index.
3. Fill **Where** with the file and symbol, and the body with what goes wrong, what the user
   sees, and the evidence — quoted from a persisted artifact (a log, a command's output, a
   test's failure), never retold from memory. Say how each number was captured.
4. Record **Suggested fix** as a hypothesis. Name the smallest change that makes the failing
   case pass, name what must not change with it, and name the alternative you considered.
   A reader inherits your frame; give them the option space, not one option.
5. For `high` severity, fill the evidence-boundary line: what the evidence is silent about,
   and what would have to be observed to settle it. An isolated reproduction under-determines
   both the diagnosis and the fix, and the line is where that is said.
6. Run `keelline bugs check`. A `dangling-mention` names an identifier the code cites with
   no entry behind it; a `stale-index` means step 2's index needs `keelline bugs index`.
7. Cite the entry by its bare identifier in the code, the plan or the commit that touches it.
   Never bracket an identifier as a wiki-link: links address notes, and a bracketed
   identifier is a permanent dangling edge.

What this skill does not do: fix the defect, or decide that it will not be fixed. Both are a
later change's, with the entry as its input.
