"""Every runtime module imports only the standard library and keelline itself.

Hooks run under whatever python3 the wrapper finds, before any environment exists, so a
third-party import works on the developer's machine and fails inside a hook on the next one.
`sys.stdlib_module_names` belongs to the running interpreter, which is why CI runs this on
every supported version. Dynamic imports (`importlib.import_module`) are resolved by name
inside the package and are covered by the discovery tests, not by this walk.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "keelline"
ALLOWED = set(sys.stdlib_module_names) | {"keelline"}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_runtime_modules_import_only_the_standard_library() -> None:
    # One parse per file: the walrus keeps CI from reading and parsing the package twice on
    # each of three interpreters.
    offenders = {
        str(path.relative_to(SRC)): sorted(offending)
        for path in SRC.rglob("*.py")
        if (offending := imported_roots(path) - ALLOWED)
    }
    assert offenders == {}


def test_the_boundary_walk_sees_the_cli_module() -> None:
    # No mutation of its own: this assertion is the mutation guard for the test above, which
    # passes vacuously if the walk ever stops finding files, and it fails exactly under the
    # condition — an empty walk — that it exists to make loud.
    assert (SRC / "cli.py") in set(SRC.rglob("*.py"))
