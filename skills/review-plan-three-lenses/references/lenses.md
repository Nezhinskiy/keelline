# The three lenses

**Premise** asks whether the plan describes the tree it will be executed against. The
failure it catches: a task written against a state the tree has already left — a finding
fixed by a later change, a signature that moved, a file that does not exist. The check is
mechanical: open every file the task names; run every command the task says already works.
Where a task cites a mechanism ("the loader validates paths"), follow the *field* through
that mechanism to its origin; the mechanism's existence is not the field's coverage.

**Oracle** asks whether the plan's assertions prove what they claim. The failure it catches:
a predicted mutation that reddens for another reason, an assertion that cannot fail, an
expectation read from the subject, a bound that is trivially true. The check: for each
assertion, name the concrete regression that would redden it, and check that nothing else
would redden first. The ten shapes are listed in the `sweep-defect-class` skill's
reference.

**Boundary** asks whether every trust decision names its anchor. The failure it catches: a
containment measured against a value the contained party controls; a write by path where a
contained primitive exists; a repository-authored string reaching the model unwrapped; a
capability granted by a flag a model can type. The check: for each ruling, write the
sentence "Y comes from <origin>, which <party> cannot move because <reason>" and see whether
it is true. If the sentence cannot be written, the ruling is not one.

Verdicts: **holds**, **fix before dispatch** (the plan text changes), **fix in the task**
(the implementer is told), **critical** (the plan does not proceed until the boundary
finding is resolved).
