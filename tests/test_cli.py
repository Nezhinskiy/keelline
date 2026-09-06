from __future__ import annotations

import subprocess
import sys

import pytest

from keelline import __version__
from keelline.cli import main


def test_version_flag_prints_the_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--version"])
    assert raised.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_module_entry_point_runs_without_the_console_script() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "keelline", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert __version__ in completed.stdout
