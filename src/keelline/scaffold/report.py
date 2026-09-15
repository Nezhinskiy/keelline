"""What a user reads before saying yes.

The count line names every outcome including the zeros, so "nothing was skipped" is something
the report says rather than something the reader has to notice is missing.
"""

from __future__ import annotations

from keelline.scaffold.model import WRITING, Plan, Verb


def render_report(planned: Plan) -> str:
    lines = [f"{action.verb:<14} {action.target}  ({action.reason})" for action in planned.actions]
    if planned.unchanged:
        lines.append(f"{'unchanged':<14} {', '.join(sorted(planned.unchanged))}")
    if planned.refusals:
        lines.append("")
        lines.append("REFUSED — nothing will be written while any of these stands:")
        lines += [f"  {r.target}  ({r.reason})" for r in planned.refusals]
    created = sum(1 for a in planned.actions if a.verb is Verb.CREATE)
    updated = sum(1 for a in planned.actions if a.verb in WRITING and a.verb is not Verb.CREATE)
    removed = sum(1 for a in planned.actions if a.verb is Verb.REMOVE)
    skipped = sum(1 for a in planned.actions if a.verb is Verb.SKIP_MODIFIED)
    lines.append("")
    lines.append(
        f"{created} to create, {updated} to update, {removed} to remove, "
        f"{skipped} skipped, {len(planned.unchanged)} unchanged, {len(planned.refusals)} refused"
    )
    return "\n".join(lines)
