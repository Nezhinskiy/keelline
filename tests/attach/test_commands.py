"""The `attach` and `detach` command surface: the flags, the exit codes and what they print.

Exit codes are C5's: 0 attached or clean, 1 a mismatch under `--check`, 2 a refusal. The
distinction is the contract §5.2 states — a mismatch under `--check` is a finding, because the
answer is "ask the owner", and `attach` itself is what refuses.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run
from tests.attach.test_binding import _machine, _project_and_store
from tests.attach.test_write import LEDGER, RULE, SETTINGS, _overlay_grants

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


@pytest.fixture(autouse=True)
def _never_the_developers_own_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test here may reach the real `~/.claude/`.

    `attach` takes a `home` for exactly this reason and the CLI passes none, because in
    production the answer is the machine owner's own home directory — so the seam a command
    test has to close is `Path.home` itself.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def _flags(root: Path, store: Path, machine: Path) -> list[str]:
    return ["--root", str(root), "--store", str(store), "--machine", str(machine)]


def test_the_two_commands_are_discovered() -> None:
    help_text = build_parser(discover_registrars()).format_help()
    assert "attach" in help_text and "detach" in help_text


def test_check_reports_the_diff_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, store = _project_and_store(tmp_path, recorded=None, origin="git@example.com:o/p.git")
    _overlay_grants(store, allow=(RULE,))
    machine = _machine(tmp_path, overlay=store.parents[2])
    assert invoke(["attach", "--check", *_flags(root, store, machine), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["added_allow"] == [RULE]
    assert data["widens"] is True
    assert data["state"] == "unbound"
    assert not (root / SETTINGS).exists()


def test_a_mismatch_under_check_is_a_finding_and_not_a_refusal(tmp_path: Path) -> None:
    # Exit 1, deliberately: the answer is "ask the owner", and a caller that reads 2 as
    # permission must never see one here. `attach` without `--check` is what refuses.
    root, store = _project_and_store(
        tmp_path, recorded="git@example.com:o/real.git", origin="git@example.com:evil/p.git"
    )
    _overlay_grants(store)
    assert (
        invoke(
            [
                "attach",
                "--check",
                *_flags(root, store, _machine(tmp_path, overlay=store.parents[2])),
            ]
        )
        == 1
    )


def test_attach_without_a_store_is_refused_rather_than_defaulted(tmp_path: Path) -> None:
    # A default here would be a store chosen by nobody, on a command whose whole point is that
    # the owner chose one.
    assert invoke(["attach", "--root", str(tmp_path)]) == 2


def test_a_widening_without_yes_exits_two_and_a_confirmed_one_exits_zero(tmp_path: Path) -> None:
    root, store = _project_and_store(tmp_path, recorded=None, origin="git@example.com:o/p.git")
    _overlay_grants(store, allow=(RULE,))
    machine = _machine(tmp_path, overlay=store.parents[2])
    assert invoke(["attach", *_flags(root, store, machine)]) == 2
    assert not (root / SETTINGS).exists()
    assert invoke(["attach", "--yes", *_flags(root, store, machine)]) == 0
    assert (root / LEDGER).is_file()


def test_detach_undoes_an_attach_through_the_command_surface(tmp_path: Path) -> None:
    # The round trip at the surface a person actually uses, and the exit codes C5 states: 0 for
    # both halves, because neither is a finding.
    root, store = _project_and_store(tmp_path, recorded=None, origin="git@example.com:o/p.git")
    _overlay_grants(store, allow=(RULE,))
    (store.parents[2] / "common" / "memory").mkdir(parents=True, exist_ok=True)
    machine = _machine(tmp_path, overlay=store.parents[2])
    assert invoke(["attach", "--yes", *_flags(root, store, machine)]) == 0
    assert invoke(["detach", "--root", str(root), "--machine", str(machine)]) == 0
    assert not (root / LEDGER).exists()
    assert not (root / SETTINGS).exists()


def test_detach_on_a_repository_that_was_never_attached_is_a_finding(tmp_path: Path) -> None:
    # Exit 1 and not 2: nothing crossed a boundary, there is simply nothing recorded — and the
    # answer is to say so rather than to guess which rules were Keelline's.
    root, _ = _project_and_store(tmp_path, recorded=None, origin="git@example.com:o/p.git")
    assert invoke(["detach", "--root", str(root)]) == 1
