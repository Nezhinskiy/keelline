from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from keelline import __version__

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "keelline"


def test_the_launcher_runs_from_the_plugin_root() -> None:
    completed = subprocess.run(
        [sys.executable, str(LAUNCHER), "--version"], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0
    assert __version__ in completed.stdout


def test_the_floor_check_precedes_every_keelline_import() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert text.index("sys.version_info < (3, 11)") < text.index("from keelline")


def _old_python() -> str | None:
    for candidate in ("python3.9", "python3.10", "/usr/bin/python3"):
        path = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
        if not path:
            continue
        probe = subprocess.run(
            [path, "-c", "import sys; print(sys.version_info < (3, 11))"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.stdout.strip() == "True":
            return path
    return None


def test_an_old_interpreter_is_refused_with_a_reason() -> None:
    old = _old_python()
    if old is None:
        pytest.skip("no interpreter below 3.11 on this machine")
    completed = subprocess.run(
        [old, str(LAUNCHER), "--version"], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 2
    assert "3.11 or newer" in completed.stderr
