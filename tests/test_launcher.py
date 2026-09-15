from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from keelline import __version__

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "keelline"


def test_the_launcher_runs_from_the_plugin_root() -> None:
    # -S suppresses site, so the venv's keelline.pth (an ambient editable install of the
    # package under test) never runs. Without -S, the interpreter would already have
    # `keelline` importable before the launcher does anything, and this test would pass
    # even if the launcher's own sys.path insertion were deleted. With -S there is no
    # site-packages at all, so the only way the import can succeed is the launcher's own
    # insertion — which is also the stdlib-only constraint in action.
    completed = subprocess.run(
        [sys.executable, "-S", str(LAUNCHER), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert __version__ in completed.stdout


def test_the_floor_check_precedes_every_keelline_import() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert text.index("sys.version_info < (3, 11)") < text.index("from keelline")


# The environment variable CI sets from `actions/setup-python`'s own `python-path` output.
#
# Without it this test skipped on every machine that has ever run it — "no interpreter below
# 3.11 on this machine" — and CI installed none, so `scripts/keelline`'s version guard, the only
# thing between a Python 3.9 user and a `SyntaxError`, was asserted nowhere, ever. A skip is
# also invisible under `-q`, so nothing said so.
OLD_PYTHON_ENV = "KEELLINE_OLD_PYTHON"


def _is_below_the_floor(path: str) -> bool:
    probe = subprocess.run(
        [path, "-c", "import sys; print(sys.version_info < (3, 11))"],
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.stdout.strip() == "True"


def _old_python() -> str | None:
    named = os.environ.get(OLD_PYTHON_ENV)
    if named:
        # Named explicitly, so a wrong answer is a failure rather than a skip: the whole point
        # of setting it is to stop this test from quietly not running.
        assert Path(named).is_file(), f"{OLD_PYTHON_ENV}={named!r} is not a file"
        assert _is_below_the_floor(named), f"{OLD_PYTHON_ENV}={named!r} is not below 3.11"
        return named
    for candidate in ("python3.9", "python3.10", "/usr/bin/python3"):
        path = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
        if path and _is_below_the_floor(path):
            return path
    return None


def test_an_old_interpreter_is_refused_with_a_reason() -> None:
    old = _old_python()
    if old is None:
        pytest.skip(f"no interpreter below 3.11 on this machine; set {OLD_PYTHON_ENV} to pin one")
    completed = subprocess.run(
        [old, str(LAUNCHER), "--version"], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 2
    assert "3.11 or newer" in completed.stderr
