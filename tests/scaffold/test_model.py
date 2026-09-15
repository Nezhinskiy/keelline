from __future__ import annotations

import pytest

from keelline.scaffold.manifest import Kind
from keelline.scaffold.model import Action, Plan, Refused, Template, Verb


def test_the_six_verbs_are_exactly_the_frozen_set() -> None:
    assert {v.value for v in Verb} == {
        "create",
        "update",
        "skip_modified",
        "remove",
        "region_update",
        "entries_update",
    }


def test_writes_lists_the_targets_apply_would_touch() -> None:
    plan = Plan(
        actions=(
            Action(Verb.CREATE, "a", "AGENTS.md", "x", "new", None),
            Action(Verb.SKIP_MODIFIED, "b", "docs/x.md", None, "hand-edited", None),
            Action(Verb.REMOVE, "c", "docs/y.md", None, "retired", None),
        ),
        refusals=(Refused("d", "../outside", "escapes the root"),),
        unchanged=("e",),
    )
    assert plan.writes == ["AGENTS.md", "docs/y.md"]


def test_a_template_renders_on_demand() -> None:
    calls: list[int] = []

    def render() -> str:
        calls.append(1)
        return "body"

    template = Template(id="a", kind=Kind.TEMPLATE, target="AGENTS.md", source="p", render=render)
    assert calls == []
    assert template.render() == "body"


def test_a_plan_cannot_be_changed_after_it_is_rendered() -> None:
    # `frozen=True` with `list` fields froze the bindings and nothing else, so the plan a user
    # approved through `render_report` could be appended to — or have an action's target
    # rewritten — before `apply` consumed it. That weakens the one claim the plan/apply split
    # exists to make: "the report a user approves is produced by the same code path that then
    # runs".
    planned = Plan(
        actions=(Action(Verb.CREATE, "a", "AGENTS.md", "x", "new", None),),
        refusals=(),
        unchanged=("e",),
    )
    with pytest.raises(AttributeError):
        planned.actions.append(  # type: ignore[attr-defined]
            Action(Verb.REMOVE, "z", "/etc/passwd", None, "smuggled", None)
        )
    assert len(planned.actions) == 1
