"""Every configured gate as a value: the five built-ins in the loader's order, each finding what
its area's command finds, and a project's own gate as its argv — bounded, and ended whole."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from keelline.assess.gates import (
    BASE,
    BUILTIN,
    GateContext,
    GateResult,
    configured,
    run_gates,
)
from keelline.cli import build_parser, discover_registrars
from keelline.config.loader import load
from keelline.config.schema import BUILTIN_GATES, Config, CustomGate, Gates
from keelline.errors import Failure
from tests.assess.smoke import BASE as SMOKE_BASE
from tests.assess.smoke import FIXTURE, smoke_repo
from tests.gitfixture import git

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

# A child the command starts, which writes a marker after 1.5 s: the gate's bound is 1 s, so a
# gate that ended only the command it started leaves this one to write.
DELAYED_WRITER = (
    "import subprocess, sys, time\n"
    "subprocess.Popen([sys.executable, '-c', "
    "'import pathlib, sys, time; time.sleep(1.5); pathlib.Path(sys.argv[1]).write_text(\"x\")', "
    "sys.argv[1]])\n"
    "time.sleep(30)\n"
)


def fixture_config(tmp_path: Path) -> Config:
    """The smoke fixture's configuration, read in place: a custom gate needs no repository."""
    return load(FIXTURE, machine=tmp_path / "m.toml")


def smoke(tmp_path: Path) -> tuple[Path, Config]:
    root = smoke_repo(tmp_path)
    return root, load(root, machine=tmp_path / "m.toml")


def results(root: Path, config: Config, *names: str, base: str = SMOKE_BASE) -> list[GateResult]:
    return list(run_gates(GateContext(root, config, base), names or config.gate_names))


def with_custom(config: Config, argv: list[str], *, seconds: int = 60) -> Config:
    gates = Gates(
        builtin=(), custom_timeout_seconds=seconds, custom={"probe": CustomGate(tuple(argv))}
    )
    return replace(config, gates=gates)


def test_the_built_in_gates_are_the_loader_s_vocabulary_in_its_order() -> None:
    # The loader validates `[gates] builtin` against `BUILTIN_GATES`; a gate it accepts that
    # this table does not hold is a `KeyError` at run time. Mutation (advisory): delete the
    # `bugs` entry from `BUILTIN` — this reddens.
    assert tuple(gate.name for gate in BUILTIN) == BUILTIN_GATES


def test_each_gate_s_command_is_one_the_real_parser_accepts() -> None:
    # `command` is what a remedy tells a person to run, so it must be a command. Mutations
    # (advisory): `"docs trail --check"` becomes `"trail --check"` (no such group), and
    # `"bugs check"` becomes `"bugs"` (a group alone has no `func`) — each reddens.
    parser = build_parser(discover_registrars())
    for gate in BUILTIN:
        args = parser.parse_args(shlex.split(gate.command.replace(BASE, "0" * 40)))
        assert callable(getattr(args, "func", None)), gate.command


@needs_git
def test_the_smoke_fixture_passes_every_gate(tmp_path: Path) -> None:
    root, config = smoke(tmp_path)
    found = results(root, config)
    assert [result.name for result in found] == list(BUILTIN_GATES)
    assert [result for result in found if result.failing] == []


@needs_git
def test_the_docs_gate_finds_an_over_budget_agents_file(tmp_path: Path) -> None:
    root, config = smoke(tmp_path)
    (root / config.paths.agents_md).write_text("line\n" * 400, encoding="utf-8")
    [docs] = results(root, config, "docs")
    assert "agents-lines" in [finding.rule for finding in docs.findings]


@needs_git
def test_the_bugs_gate_finds_a_broken_entry(tmp_path: Path) -> None:
    root, config = smoke(tmp_path)
    entry = root / config.paths.bugs / "BR-001.md"
    entry.write_text(entry.read_text(encoding="utf-8") + "<<<<<<< ours\n", encoding="utf-8")
    [bugs] = results(root, config, "bugs")
    assert "conflict-marker" in [finding.rule for finding in bugs.findings]


@needs_git
def test_the_plan_gate_finds_a_plan_the_change_touches(tmp_path: Path) -> None:
    root, config = smoke(tmp_path)
    (root / config.paths.plans / "2026-09-20-new.md").write_text("# New\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "docs: a plan with no scope")
    [plan] = results(root, config, "plan")
    assert "scope-missing" in [finding.rule for finding in plan.findings]


@needs_git
def test_the_commit_gate_finds_an_attribution_trailer_after_the_base(tmp_path: Path) -> None:
    root, config = smoke(tmp_path)
    message = "fix: a change\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
    git(root, "commit", "-q", "--allow-empty", "-m", message)
    sha = git(root, "rev-parse", "HEAD").strip()
    [commit] = results(root, config, "commit")
    assert [(finding.rule, finding.path) for finding in commit.findings] == [("attribution", sha)]


@needs_git
def test_a_stale_trail_is_a_failing_gate(tmp_path: Path) -> None:
    # The fixture's own listing is current, so the pass case cannot see the stale arm.
    root, config = smoke(tmp_path)
    (root / config.paths.plans / "2026-09-20-new.md").write_text("# New\n", encoding="utf-8")
    git(root, "add", "-A")
    [trail] = results(root, config, "trail")
    assert [finding.rule for finding in trail.findings] == ["trail-stale"]
    assert trail.failing


@needs_git
def test_a_commit_range_git_cannot_read_is_a_gate_that_did_not_answer(tmp_path: Path) -> None:
    # `check_range` refuses a range git cannot read. A gate that could not judge the tree is
    # failing, and its reason names the command with the base's placeholder, never the base:
    # the base is whatever a caller was handed.
    root, config = smoke(tmp_path)
    [commit] = results(root, config, "commit", base="no-such-ref")
    assert not commit.answered
    assert commit.failing
    assert "`keelline commit check --range <base>..HEAD`" in commit.reason
    assert "no-such-ref" not in commit.reason


def test_a_name_the_configuration_does_not_hold_is_a_caller_s_bug(tmp_path: Path) -> None:
    # Callers validate names first; one that reaches here is their bug, not a gate that passed.
    # Mutation (advisory): `wanted = {gates[name].name for name in names}` becomes
    # `wanted = set(names)` — the unknown name is silently dropped and this reddens.
    config = with_custom(fixture_config(tmp_path), ["true"])
    with pytest.raises(KeyError):
        run_gates(GateContext(tmp_path, config, SMOKE_BASE), ["lint"])


@needs_git
def test_each_named_gate_runs_once_in_the_configured_order(tmp_path: Path) -> None:
    root, config = smoke(tmp_path)
    found = results(root, config, "trail", "docs", "trail")
    assert [result.name for result in found] == ["docs", "trail"]


@needs_git
def test_a_gate_that_raises_did_not_answer_and_every_gate_after_it_still_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `docs_gate` looks `check_budgets` up in its own module at call time, so the patch reaches
    # it through the function `gates` holds. The exception's text quotes the repository, and
    # must not travel into the reason.
    root, config = smoke(tmp_path)

    def raising(*args: object) -> list[object]:
        raise Failure("a message that quotes the repository")

    monkeypatch.setattr("keelline.docs.hygiene.check_budgets", raising)
    found = results(root, config)
    [docs] = [result for result in found if result.name == "docs"]
    assert not docs.answered
    assert "`keelline docs check`" in docs.reason
    assert "quotes" not in docs.reason
    assert [result.name for result in found if not result.answered] == ["docs"]
    assert [result.name for result in found] == list(BUILTIN_GATES)


def test_the_configured_set_is_the_kept_built_ins_then_the_custom_gates(tmp_path: Path) -> None:
    # Mutation (advisory): `configured` returning every built-in and every custom gate, whatever
    # `[gates] builtin` keeps — this reddens.
    root = tmp_path / "project"
    root.mkdir()
    fixture = (FIXTURE / "keelline.toml").read_text(encoding="utf-8")
    gates = '\n[gates]\nbuiltin = ["docs"]\n\n[gates.custom.probe]\nrun = ["true"]\n'
    (root / "keelline.toml").write_text(fixture + gates, encoding="utf-8")
    config = load(root, machine=tmp_path / "m.toml")
    assert list(configured(config)) == ["docs", "probe"]


def test_a_custom_gate_that_exits_zero_passes(tmp_path: Path) -> None:
    # Mutation (advisory): `if code == 0:` becomes `if False:` — a passing command is one
    # finding and this reddens.
    config = with_custom(fixture_config(tmp_path), [sys.executable, "-c", "pass"])
    [probe] = results(tmp_path, config)
    assert probe.answered
    assert not probe.failing


def test_a_custom_gate_that_exits_non_zero_is_one_finding_and_its_output_passes_through(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    # The command's bytes are the project's own and reach the terminal untouched — on standard
    # error, so `--json` on standard output stays one object — and reach no result: nothing
    # in the module reads them. One property per assertion below.
    marker = "keelline-probe-output"
    script = f"import sys; sys.stdout.write('\\x1b[31m{marker}\\n'); sys.exit(3)"
    config = with_custom(fixture_config(tmp_path), [sys.executable, "-c", script])
    [probe] = results(tmp_path, config)
    assert [(finding.rule, finding.detail) for finding in probe.findings] == [
        ("exit-status", "exited 3")
    ]
    out, err = capfd.readouterr()
    assert out == ""
    assert f"\x1b[31m{marker}" in err
    assert marker not in repr(probe)


def test_a_custom_gate_past_its_time_limit_did_not_answer(tmp_path: Path) -> None:
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    config = with_custom(fixture_config(tmp_path), command, seconds=1)
    [probe] = results(tmp_path, config)
    assert not probe.answered
    assert probe.failing
    assert (
        probe.reason == "the command [gates.custom.probe] run names could not start, or ran past 1s"
    )


def test_a_custom_gate_past_its_time_limit_leaves_nothing_running(tmp_path: Path) -> None:
    # A timeout case with one sleeping process cannot show this: it is the descendant — a test
    # runner a shell wrapper started — that must not run on after the gate has reported.
    marker = tmp_path / "written-after-the-gate-reported"
    command = [sys.executable, "-c", DELAYED_WRITER, str(marker)]
    config = with_custom(fixture_config(tmp_path), command, seconds=1)
    [probe] = results(tmp_path, config)
    assert not probe.answered
    time.sleep(2.5)
    assert not marker.exists()


def test_an_interrupted_custom_gate_leaves_nothing_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A terminal's Ctrl-C reaches Keelline's process group and not the command's own session,
    # so nothing but the gate itself can end the command's tree on the way out.
    marker = tmp_path / "written-after-keelline-left"
    command = [sys.executable, "-c", DELAYED_WRITER, str(marker)]
    config = with_custom(fixture_config(tmp_path), command, seconds=600)
    real = subprocess.Popen.wait
    calls: list[float | None] = []

    def interrupted(self: subprocess.Popen[bytes], timeout: float | None = None) -> int:
        calls.append(timeout)
        if len(calls) == 1:
            raise KeyboardInterrupt
        return real(self, timeout=timeout)

    monkeypatch.setattr(subprocess.Popen, "wait", interrupted)
    with pytest.raises(KeyboardInterrupt):
        results(tmp_path, config)
    time.sleep(2.5)
    assert not marker.exists()


def test_a_custom_gate_whose_command_does_not_exist_did_not_answer(tmp_path: Path) -> None:
    # Mutation (advisory): drop the `except OSError:` around `Popen` — `FileNotFoundError`
    # escapes `run_gates` and this reddens.
    config = with_custom(fixture_config(tmp_path), ["no-such-command-anywhere"])
    [probe] = results(tmp_path, config)
    assert not probe.answered
    assert probe.failing
