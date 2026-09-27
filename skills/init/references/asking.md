# Asking across harnesses

The questions come from `keelline init --questions --json`: each property under
`questions.properties` is one question, its `oneOf` or `items.enum` are its options, and its
`default` is the recommendation, offered first and marked so. `project.name` and
`project.base_branch` are free text held to the property's `pattern`; the command refuses a
value outside it, naming the rule.

| Step | Up to 4 questions of up to 4 options, multi-select | Up to 3 questions of 2–3 options, no multi-select | No ask tool |
|---|---|---|---|
| 2, the card | one confirm question | one confirm question | one plain question |
| 2, corrections | the named values, in one call | the named values, three per call | one per turn |
| 3 and 4, memory and "keep any out of git?" | one call of two questions | one call of two questions | one per turn |
| 3, the overlay follow-up | a call of its own | a call of its own | one turn |
| 4, which files | one multi-select question per four ids | one free-text question listing the ids, answered comma-separated | one question listing the ids |
| 5, the final yes | one question | one question | one plain question |

- **Free text.** A name or a branch is a plain question, or the default plus the harness's own
  free-text answer where it has one.
- **Agents without multi-select.** Offer each harness alone and all of them together.
- **The overlay follow-up depends on the answer before it,** so it never shares that call.
- **Every option list stays within the limit.** A longer list is split across questions,
  never cut.
- **Silence is not consent.** A timeout, an empty answer, or "continue with your best judgment"
  never counts as a yes to write anything.
