from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable

import pytest

from keelline import __version__
from keelline.cli import Registrar, SubParsers, discover_registrars, main, run
from keelline.errors import Failure, Refusal
from keelline.result import Result


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


def _area(name: str, func: Callable[[argparse.Namespace], Result]) -> Registrar:
    def register(groups: SubParsers) -> None:
        group = groups.add_parser(name)
        sub = group.add_subparsers(dest="command", metavar="<command>")
        cmd = sub.add_parser("go")
        cmd.set_defaults(func=func)

    return register


def _ok(args: argparse.Namespace) -> Result:
    return Result("probe ran", {"n": 1})


def _failing(args: argparse.Namespace) -> Result:
    raise Failure("three findings")


def _refusing(args: argparse.Namespace) -> Result:
    raise Refusal("an absent guard is not permission")


def test_a_result_prints_its_summary_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["probe", "go"], registrars=[_area("probe", _ok)]) == 0
    assert capsys.readouterr().out.strip() == "probe ran"


def test_json_flag_works_anywhere_on_the_line(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["probe", "go", "--json"], registrars=[_area("probe", _ok)]) == 0
    assert json.loads(capsys.readouterr().out) == {"summary": "probe ran", "n": 1}
    assert run(["--json", "probe", "go"], registrars=[_area("probe", _ok)]) == 0
    assert json.loads(capsys.readouterr().out) == {"summary": "probe ran", "n": 1}


def test_failure_exits_one_and_refusal_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["probe", "go"], registrars=[_area("probe", _failing)]) == 1
    assert "three findings" in capsys.readouterr().err
    assert run(["probe", "go"], registrars=[_area("probe", _refusing)]) == 2
    assert "refused: an absent guard" in capsys.readouterr().err


def test_failures_emit_json_when_asked(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["probe", "go", "--json"], registrars=[_area("probe", _failing)]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "failed"


@pytest.mark.xfail(strict=True, reason="the release area lands in Task 8")
def test_areas_are_discovered_from_the_package() -> None:
    names = {registrar.__module__ for registrar in discover_registrars()}
    assert "keelline.release.commands" in names
