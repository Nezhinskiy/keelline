# The audit protocol

**A candidate is executable or it is not a candidate.** "The parser may mishandle
quotes" is a worry. "`keelline commit strip <path>` on a message whose trailer line contains a
quoted colon leaves the trailer in place — run it on this file and diff" is a candidate.
The difference is the command.

**Verdicts.**

- *confirmed* — the command showed the claim false. The output is quoted in the entry.
- *refuted* — the command showed the claim true, or the failure path unreachable. The
  refutation is recorded with the candidate, because a refuted candidate is regenerated
  by every later audit that does not know it was refuted.
- *plausible* — a gap you can describe and could not make fail. Recorded, not filed;
  a later change that touches the component reads it.

**What a verification owes.** The real module, on the real interpreter, over the real
tree; both branches when a regression is claimed; a search for the actual boundary rather
than acceptance of the candidate's. Present the executed matrix. Never treat one reviewer's
"sound" as clearing a surface another flagged.

**Severity.** By what the defect costs the user, on the ledger's own scale. A containment
or trust-gate bypass is reported through the security policy and never as a public entry.

**Scope discipline.** An audit finds; it does not fix. A finding fixed in passing is a
finding nobody can tell from one that was never there.
