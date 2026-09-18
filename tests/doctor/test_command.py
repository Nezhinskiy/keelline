"""The `doctor` command: one line, the right exit code, and a remedy the skill can relay.

The report itself is `tests/doctor/test_checks.py`'s. What is untested until this file is the
argparse wiring, the two exit codes §5.2 and C5 fix, and the one property of the output that
decides whether the skill is any use: a remedy missing from `--json` is a remedy the user never
sees.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run
from keelline.doctor.api import OK, RED, SKIP, WARN, Check
from keelline.doctor.commands import summarise
from keelline.findings import LISTED_LIMIT
from tests.doctor.test_checks import _initialised


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def test_the_command_is_discovered() -> None:
    assert "doctor" in build_parser(discover_registrars()).format_help()


def test_a_clean_installation_exits_zero_with_one_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # §5.2: every command prints a one-line result. Fifteen rows on stdout would make `doctor`
    # the one command a caller has to parse rather than read, and `--json` is where the rows are.
    root = _initialised(tmp_path)
    code = invoke(["doctor", "--root", str(root), "--home", str(tmp_path / "home")])
    out = capsys.readouterr().out
    assert code == 0
    assert len(out.strip().splitlines()) == 1


def test_a_skip_is_not_a_finding(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Three checks skip in this build by construction (release hashes, Codex trust, [ci] ref).
    # If a skip exited 1, `doctor` would be red on every correct installation until wave 5.
    root = _initialised(tmp_path)
    code = invoke(["doctor", "--root", str(root), "--home", str(tmp_path / "home"), "--json"])
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert [check["name"] for check in report["checks"] if check["status"] == "skip"]


def test_any_red_check_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Exit 1 is "findings" (C5). A doctor that always exits 0 is a doctor nothing can gate on,
    # and the `assess` lane in wave 5 will want to. A directory with no `keelline.toml` is the
    # cheapest red there is, and §12's own first row.
    code = invoke(["doctor", "--root", str(tmp_path), "--home", str(tmp_path / "home")])
    assert code == 1
    assert "not-initialised" in capsys.readouterr().out


def test_the_json_form_carries_every_check_and_its_remedy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The skill relays remedies verbatim, so a remedy missing from `--json` is a remedy the
    # user never sees — and the summary line has room for none of them.
    code = invoke(["doctor", "--root", str(tmp_path), "--home", str(tmp_path / "home"), "--json"])
    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert len(report["checks"]) == 15
    assert all({"name", "status", "detail", "remedy"} <= set(check) for check in report["checks"])
    red = next(check for check in report["checks"] if check["status"] == "red")
    assert red["remedy"]


def test_the_summary_line_is_bounded() -> None:
    # `findings.LISTED_LIMIT` exists because an unbounded summary pushes the repairing command
    # off the end of the line, and fifteen checks is already past eight. Asserted over a
    # synthetic report rather than a fixture, because arranging nine simultaneous real failures
    # would be a test about the fixture.
    checks = [Check(f"check-{n}", RED, "d", "r") for n in range(LISTED_LIMIT + 3)]
    summary = summarise(checks)
    assert len(summary.splitlines()) == 1
    assert "and 3 more" in summary
    assert "check-10" not in summary


def test_the_summary_counts_every_status(tmp_path: Path) -> None:
    # The vacuity guard for the line above: a summary that named only the red rows would pass
    # it while saying nothing about a warning or a skip.
    summary = summarise(
        [
            Check("a", OK, "", ""),
            Check("b", WARN, "", ""),
            Check("c", SKIP, "", ""),
            Check("d", RED, "", ""),
        ]
    )
    assert "1 red" in summary
    assert "1 warn" in summary
    assert "1 skipped" in summary
