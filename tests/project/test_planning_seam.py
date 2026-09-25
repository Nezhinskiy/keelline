"""Every footprint command plans through `project.footprint.Passes`, and nothing else in the
project area plans at all.

`Passes` binds the ownership relation into every plan and runs the ignore guard over every
prediction, so a command that plans through it cannot leave either behind. The engine's own
`plan` keeps its `owners` keyword optional, because the overlay lane keeps nothing out of git and
has no relation to pass; so the seam is what holds the project area, and this is what holds the
seam. Required instead, the keyword would make every overlay call and a hundred engine tests say
`owners=None`, and would still let a new command (`adopt`) pass `None` beside them: the bypass
is importing the planner, so that is what is checked.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AREA = ROOT / "src" / "keelline" / "project"
SEAM = AREA / "footprint.py"
# The planner and what binds its guards: the engine's plan and the two lookups that take the
# relation, and the ignore guard.
PLANNERS = {
    "keelline.scaffold": {"plan", "left_copies", "local_copies"},
    "keelline.scaffold.engine": {"plan", "left_copies", "local_copies"},
    "keelline.project.ignored": {"refuse_ignored"},
}


def _planners_reached(path: Path) -> set[str]:
    """Each planner name `path` imports, or reaches as an attribute of a module it imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    modules: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                if alias.name in PLANNERS.get(node.module, set()):
                    found.add(alias.name)
                qualified = f"{node.module}.{alias.name}"
                if qualified in PLANNERS:
                    modules[alias.asname or alias.name] = qualified
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in PLANNERS:
                    modules[alias.asname or alias.name] = alias.name
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.attr in PLANNERS.get(modules.get(node.value.id, ""), set())
        ):
            found.add(node.attr)
    return found


def test_only_the_planning_seam_imports_the_planner_or_the_ignore_guard() -> None:
    # The walk first: the seam itself must be seen reaching all of them, or a check that
    # matched nothing would pass every module. Mutation (oracle): "a footprint command imports
    # the planner past the seam" -> `init` imports `plan` again, and this reddens.
    assert _planners_reached(SEAM) == {"plan", "left_copies", "local_copies", "refuse_ignored"}
    modules = sorted(p for p in AREA.glob("*.py") if p != SEAM)
    assert len(modules) >= 10, modules
    reached = {p.name: _planners_reached(p) for p in modules}
    assert {name: found for name, found in reached.items() if found} == {}
