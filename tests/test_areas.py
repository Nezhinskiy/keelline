"""One discovery loop for both registries, and a probe that skips the areas it rejects."""

from __future__ import annotations

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


def test_an_area_with_no_such_submodule_is_never_imported() -> None:
    # `keelline hook` is a subprocess per tool call, so discovery importing an area only to
    # learn it registers nothing is paid on the hot path.
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
