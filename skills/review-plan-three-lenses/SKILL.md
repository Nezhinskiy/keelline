---
name: review-plan-three-lenses
description: Review an implementation plan through three lenses before it is executed — whether each task's premise holds in the tree, whether each assertion can fail, and whether each trust ruling names its anchor. Use on any plan longer than one task, before the first dispatch.
---

# Reviewing a plan through three lenses

Go through the plan once end to end, then once per lens. Each lens produces findings with a task
number and a verdict; a finding with no task number is a finding about the plan's header.
The lenses are defined in [references/lenses.md](references/lenses.md); this is the
procedure.

1. **Premise.** For every task, open the files it names and check its founding claim against
   the tree: the function exists with that signature, the line it quotes is there, the
   behaviour it says is absent is absent. A plan is wrong more often than the tree is. Where
   the plan cites a mechanism by name, trace the field the mechanism is supposed to cover;
   a name proves existence, not coverage.
2. **Oracle.** For every assertion, ask whether it can fail, and whether the predicted
   mutation reddens it for the reason it names. An `Expected:` line is a hypothesis; a
   mutation that would redden at import, or for a collateral reason, needs redesigning
   before an implementer inherits it.
3. **Boundary.** For every rule of the form "refuse X inside Y", "trust Z", "read from W":
   name Y's, Z's and W's provenance, and say why the party being contained cannot move it.
   Every write goes through a contained primitive; repository bytes reach the model only as
   data. A ruling whose anchor arrives through the channel it exists to defeat is a critical
   finding, whatever else is right about it.
4. Run the lint the plan is held to: `keelline plan check docs/plans/example.md`, and
   `keelline docs check` for the documents it links.
5. Set the findings out as a table — id, lens, task, finding, verdict — and give it to the
   plan's author neutrally. Do not grade a concern before the author has answered it; twice
   in one execution a reviewer overturned the controller's own leaning, and pre-judging
   would have cost both.

A plan that passes all three lenses can still be too large per dispatch. Say so as a
separate finding: it is a cost, not a defect.
