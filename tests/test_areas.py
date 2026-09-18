"""One discovery loop for both registries, and a probe that skips the areas it rejects."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from keelline.areas import area_modules
from keelline.cli import discover_registrars

ROOT = Path(__file__).resolve().parents[1]
LIST_IMPORTS = (
    "import sys\n"
    "from keelline.hooks.registry import discover\n"
    "discover()\n"
    "print(' '.join(sorted(m for m in sys.modules if m.startswith('keelline'))))\n"
)


def test_commands_modules_are_found_in_area_name_order() -> None:
    names = [module.__name__ for module in area_modules("commands")]
    assert names == sorted(names)
    assert "keelline.hooks.commands" in names
    assert "keelline.release.commands" in names


def test_the_cli_registry_reads_the_same_discovery_as_the_helper() -> None:
    assert [registrar.__module__ for registrar in discover_registrars()] == [
        module.__name__ for module in area_modules("commands")
    ]


def test_in_isolation_an_area_with_no_such_submodule_is_never_imported() -> None:
    # Deliberately isolates `discover()` from the CLI frame: the subprocess never calls
    # `discover_registrars()`, so nothing has imported the area packages beforehand. Production
    # is not this shape — `main()` runs `discover_registrars()` first, which already imports
    # every area's `commands` submodule before `hook` ever reaches this probe — but the helper's
    # own behaviour still holds here: given a clean interpreter, `area_modules` imports only the
    # areas that actually carry the requested submodule.
    completed = subprocess.run(
        [sys.executable, "-c", LIST_IMPORTS],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src")},
    )
    assert completed.returncode == 0, completed.stderr
    imported = completed.stdout.split()
    assert "keelline.hooks.registry" in imported
    assert "keelline.release" not in imported
    assert "keelline.config" not in imported
    assert "keelline.presets" not in imported


# The ten areas CONTRIBUTING lists, and the one departure from the rule below. `cli.py` is the
# CLI frame and not an area — nothing discovers it, it has no `api.py`, and it owns the wiring
# of the `hook` command — so it reads `keelline.hooks.policy` directly. It is named here rather
# than skipped silently, because an exemption nobody can see is how the two violations this
# guard exists to catch were merged green.
SURFACE_EXEMPT = frozenset({("cli.py", "keelline.hooks.policy")})


def _area_names(source: Path) -> list[str]:
    """CONTRIBUTING's definition, read off the tree: a subpackage carrying `commands.py` or
    `hooks.py`. Derived rather than listed, so a new area is covered the day it arrives."""
    return sorted(
        path.name
        for path in source.iterdir()
        if path.is_dir() and ((path / "commands.py").exists() or (path / "hooks.py").exists())
    )


def _imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    """Every module name this file imports, in both spellings.

    `from keelline.memory.api import X` and `import keelline.memory.api` are the obvious one;
    `from keelline.memory import worktree` is the one a rule that looked only at `node.module`
    would miss, and it reaches a private module just as squarely.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.append((node.lineno, node.module))
            found += [(node.lineno, f"{node.module}.{alias.name}") for alias in node.names]
    return found


def test_no_area_reaches_into_another_areas_private_module() -> None:
    # CONTRIBUTING: "`api.py` is the area's import surface. Other areas import from it and from
    # nothing else." Nothing asserted it, and an external review found the first two violations
    # in this repository's history — `memory/commands.py` importing `hooks.dispatch` and
    # `doctor/checks.py` importing `hooks.sink` — both merged green.
    #
    # Two mutations in `mutations.toml`: one puts a violation back (doctor reading the setup
    # area's private `machine` module), and one narrows the walk, because a guard that silently
    # stops walking reports no offences for the same reason a guard with nothing to report does.
    source = ROOT / "src" / "keelline"
    areas = _area_names(source)
    files = sorted(source.rglob("*.py"))
    crossings: list[str] = []
    offences: list[str] = []
    for path in files:
        parts = path.relative_to(source).parts
        here = parts[0] if len(parts) > 1 else None
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, module in _imported_modules(tree):
            bits = module.split(".")
            if len(bits) < 3 or bits[0] != "keelline" or bits[1] not in areas or bits[1] == here:
                continue
            where = str(path.relative_to(source))
            crossings.append(f"{where} -> {module}")
            if bits[2] == "api" or (where, ".".join(bits[:3])) in SURFACE_EXEMPT:
                continue
            offences.append(f"{where}:{line} imports {module}")
    # The walk is asserted before anything is asserted about it. Both floors are well under
    # today's numbers and are there to fail on a walk that stopped walking, not to be kept
    # current: measured at 99 files, 10 areas and 100 crossings when this was written, and a
    # walk narrowed to `commands.py` alone finds 13.
    assert len(areas) == 10, areas
    assert len(files) >= 70, len(files)
    assert len(crossings) >= 60, crossings
    assert not offences, "an area reached past another area's api.py:\n" + "\n".join(offences)
