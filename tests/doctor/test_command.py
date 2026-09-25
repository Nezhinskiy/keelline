"""The `doctor` command: one line, the right exit code, and a remedy the skill can relay.

The report itself is `tests/doctor/test_checks.py`'s. What is untested until this file is the
argparse wiring, the two exit codes §5.2 and C5 fix, and the one property of the output that
decides whether the skill is any use: a remedy missing from `--json` is a remedy the user never
sees.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run
from keelline.doctor import checks
from keelline.doctor.api import OK, RED, SKIP, WARN, Check
from keelline.doctor.commands import summarise
from keelline.findings import LISTED_LIMIT
from tests.doctor.test_checks import _initialised


@pytest.fixture(autouse=True)
def _nothing_of_the_developers_own(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The seam `tests/doctor/test_checks.py` closes with `_env`, closed here instead.

    `run_doctor` passes no `env=`, so `run_checks` falls back to `os.environ` — and that is the
    real environment, which the Global Constraints forbid a test from reading: `ignored-env`
    reports whichever of two real variables is set, `diagnostics` finds the harness data root in
    it and this suite is plausibly run inside a session where that points at a real log, and
    `load(root, machine=None)` resolves the developer's own `~/.config/keelline/config.toml`.
    The flag cases below cannot pass an environment through argparse, so the environment is made
    hermetic instead of passed.

    `_own_root` is stood down for the same reason and one more: `plugin_root` would otherwise
    answer with this checkout, and the `wrapper` check **executes** what it answers. Every case
    here would then spawn a real `hooks/run-hook.sh`, and `test_a_clean_installation_exits_zero`
    would become false the day that run goes red on somebody's machine — which is a fact about
    their interpreters, not about the argparse wiring this file is for. What the two checks do
    with a plugin root is `tests/doctor/test_checks.py`'s.
    """
    for name in list(os.environ):
        if name.startswith(("CLAUDE_", "PLUGIN_", "KEELLINE_", "XDG_")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(checks, "_own_root", lambda: None)


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def test_the_command_is_discovered() -> None:
    assert "doctor" in build_parser(discover_registrars()).format_help()


def test_a_clean_installation_exits_zero_with_one_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # §5.2: every command prints a one-line result. Sixteen rows on stdout would make `doctor`
    # the one command a caller has to parse rather than read, and `--json` is where the rows are.
    root = _initialised(tmp_path)
    code = invoke(["doctor", "--root", str(root), "--home", str(tmp_path / "home")])
    out = capsys.readouterr().out
    assert code == 0
    assert len(out.strip().splitlines()) == 1


def test_the_runner_this_command_builds_is_bounded_for_a_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one call this area makes that leaves the machine is bounded, and here is where it is.

    `runner.NETWORK_TIMEOUT_SECONDS` is five minutes, written for `gh repo create --clone` and
    the clone behind it. `doctor` inherited it for the `ci-ref` row's single `git ls-remote` —
    and `keelline init` recording a `[ci] ref` is what made a five-minute block reachable on a
    command §5.2 gives one line of output. The row's own `git` questions go through `gitenv`'s
    five seconds and the wrapper probe through this module's thirty, so the bound here is the
    module's own thirty and `checks.CI_REF_TIMEOUT_SECONDS` carries the argument for it.

    Asserted where the runner is *built*, because that is the only place the choice exists: the
    `Runner` protocol has no timeout and every stub in this suite is bounded at nothing. The
    factory is imported inside `run_doctor`, so patching the module attribute is the seam.

    Mutation (oracle entry "doctor asks the public repository with no bound of its own"):
    `subprocess_runner(timeout=CI_REF_TIMEOUT_SECONDS)` -> `subprocess_runner()` -> this reddens
    on the recorded keyword.
    """
    import keelline.runner as runner

    asked: list[float | None] = []
    real = runner.subprocess_runner

    def spy(*, timeout: float | None = None) -> runner.Runner:
        asked.append(timeout)
        return real(timeout=timeout)

    monkeypatch.setattr(runner, "subprocess_runner", spy)
    root = _initialised(tmp_path)
    assert invoke(["doctor", "--root", str(root), "--home", str(tmp_path / "home")]) == 0
    assert asked == [checks.CI_REF_TIMEOUT_SECONDS]
    # And it is narrower than the seam's own default, which is the whole point of asking.
    assert checks.CI_REF_TIMEOUT_SECONDS < runner.NETWORK_TIMEOUT_SECONDS


def test_a_skip_is_not_a_finding(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # One check cannot be answered by this build — the Codex hook-trust hash §10 lists as
    # unmeasured — and `ci-ref` skips on a state this repository is in: it records no `[ci] ref`.
    # (`files` was counted with the first until the release lane shipped the record it compares
    # against.) If a skip exited 1, `doctor` would be red on every correct installation.
    root = _initialised(tmp_path)
    code = invoke(["doctor", "--root", str(root), "--home", str(tmp_path / "home"), "--json"])
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert [check["name"] for check in report["checks"] if check["status"] == "skip"]


def test_any_red_check_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Exit 1 is "findings". A doctor that always exits 0 is a doctor nothing can gate on: a
    # script or a CI step that runs it reads the exit code, since `keelline assess` runs no
    # doctor check. A directory with no `keelline.toml` is the cheapest red there is, and the
    # report's own first row.
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
    assert len(report["checks"]) == 16
    assert all({"name", "status", "detail", "remedy"} <= set(check) for check in report["checks"])
    red = next(check for check in report["checks"] if check["status"] == "red")
    assert red["remedy"]


def test_the_summary_line_is_bounded() -> None:
    # `findings.LISTED_LIMIT` exists because an unbounded summary pushes the repairing command
    # off the end of the line, and sixteen checks is already past eight. Asserted over a
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
