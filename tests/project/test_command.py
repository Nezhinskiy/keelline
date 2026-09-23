"""`keelline init` through the real parser: the flags, the exit codes and the `--json` keys.

Nothing here reaches the network, and it is kept out two ways. Every case but one goes through
`_invoke`, which appends `--no-ci`: with `[ci] mode` set to `none` the run never asks the release
area to resolve a pin, so the `subprocess_runner()` `commands.py` builds is never handed a `git
ls-remote` against the public repository. The one case that must resolve a pin — the hostile
`gate_branch` arm, which exists precisely because `_ci` reaches that check *after* the pin —
stubs `subprocess_runner` at the seam `commands.py` builds it from and answers one released tag
from a string.
"""

from __future__ import annotations

import inspect
import io
import json
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run
from keelline.config.loader import loads
from keelline.config.schema import Config
from keelline.project.commands import run_init
from keelline.project.templates import _ci
from keelline.release.api import Resolution
from keelline.runner import Completed
from tests.gitfixture import git, needs_git


@dataclass
class _Listing:
    """A `Runner` that answers `ls-remote` from a string and reaches no network."""

    stdout: str

    def run(self, argv: list[str], cwd: Path) -> Completed:
        return Completed(0, self.stdout, "")


JSON_KEYS = {"dry_run", "adopted", "once", "footprint", "writes", "skipped", "pin", "asked", "note"}


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "widget"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", "git@github.com:owner/widget.git")
    return root


def _run(root: Path, tmp_path: Path, *argv: str) -> tuple[int, str]:
    parser = build_parser(discover_registrars())
    flags = ["--root", str(root), "--machine", str(tmp_path / "absent.toml")]
    with redirect_stdout(io.StringIO()) as out:
        code = run(["init", *argv, *flags], parser=parser)
    return code, out.getvalue()


def _invoke(root: Path, tmp_path: Path, *argv: str) -> tuple[int, str]:
    """`_run` with `--no-ci`, which is what keeps the network out of it."""
    return _run(root, tmp_path, *argv, "--no-ci")


@needs_git
def test_without_yes_the_command_refuses_and_names_the_lane_that_ships_the_questions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    code, printed = _invoke(root, tmp_path)
    assert code == 2 and printed == ""
    stderr = capsys.readouterr().err
    assert "onboarding lane" in stderr and "--yes" in stderr
    assert not (root / ".keelline").exists()


@needs_git
def test_a_dry_run_prints_both_reports_and_says_it_wrote_nothing(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    code, printed = _invoke(root, tmp_path, "--yes", "--dry-run", "--json")
    assert code == 0, printed
    data = json.loads(printed)
    assert set(data) >= JSON_KEYS and data["dry_run"] is True
    # Two reports, not one rendered twice: the write-once pass plans three files and the
    # footprint pass plans the rest, and a summary that showed one of them would hide
    # whichever half a refusal landed in.
    assert "CLAUDE.md" in data["once"] and "CLAUDE.md" not in data["footprint"]
    assert ".gitignore" in data["footprint"]
    assert data["adopted"] is False and data["pin"] is None
    assert set(data["writes"]) >= {"CLAUDE.md", "keelline.toml", ".gitignore"}
    assert not (root / "CLAUDE.md").exists()


@needs_git
def test_a_real_run_prints_both_reports_in_full_and_the_ci_line(tmp_path: Path) -> None:
    # Fix round 1, finding 2: the summary was four count lines, so a person without `--json` was
    # told how many files there were and never which. The skill relays "both reports … each one
    # names every file with its verdict", which it could not do from counts.
    root = _repo(tmp_path)
    code, printed = _invoke(root, tmp_path, "--yes")
    assert code == 0, printed
    assert printed.startswith("initialised:")
    assert "write-once:" in printed and "footprint:" in printed
    # Per-artifact lines, from both passes, with their verbs — not just the counts.
    assert "create         CLAUDE.md  (new)" in printed
    assert "create         docs/adr/0000-template.md  (new)" in printed
    assert "CI: skipped — [ci] mode is none" in printed
    assert (root / ".keelline" / "manifest.json").is_file()


@needs_git
def test_a_refused_footprint_exits_one_with_the_refused_section_in_that_report(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    (root / "AGENTS.md").write_text("# Mine\n\n<!-- keelline:harness:end -->\n", encoding="utf-8")
    code, printed = _invoke(root, tmp_path, "--yes", "--json")
    assert code == 1, printed
    data = json.loads(printed)
    assert "REFUSED" in data["footprint"] and "REFUSED" not in data["once"]
    assert not (root / ".keelline").exists()
    # And in plain text, which is the output a person meets on this path: the REFUSED section
    # with the artifact and the engine's reason, and a heading that does not claim otherwise.
    code, plain = _invoke(root, tmp_path, "--yes")
    assert code == 1
    assert plain.startswith("refused, and nothing was written:")
    assert "REFUSED — nothing will be written" in plain
    assert "AGENTS.md  (region 'harness' has an end marker with no beginning" in plain


@needs_git
def test_a_hostile_gate_branch_is_reported_as_a_skipped_workflow_and_not_as_a_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fix round 1, finding 1, end to end. `[ci] mode` stays `reusable` here — this is the one
    # case in this module that does not pass `--no-ci` — so the command really reaches the
    # release area; the runner it would use is stubbed at the seam `commands.py` builds it from,
    # so no network call is made and the answer is one released tag.
    from keelline import runner as runner_module

    root = _repo(tmp_path)
    # A recorded ref as well: the branch check is reached only once there is a ref to render,
    # and it is deliberately not the sha the stub listing resolves, so the assertions below can
    # tell the two sources apart.
    recorded = "e" * 40
    (root / "keelline.toml").write_text(
        '[keelline]\nversion = "0.1.0"\n\n[project]\nname = "widget"\n\n'
        f'[ci]\nref = "{recorded}"\ngate_branch = "main\'; rm -rf"\n',
        encoding="utf-8",
    )
    sha = "c" * 40
    monkeypatch.setattr(
        runner_module,
        "subprocess_runner",
        lambda: _Listing(f"{sha}\trefs/tags/v0.1.0\n"),
    )
    code, printed = _run(root, tmp_path, "--yes")
    assert code == 0, printed
    assert "CI: skipped — [ci] gate_branch is not a plain branch name" in printed
    assert sha not in printed and "v0.1.0@" not in printed
    assert not (root / ".github").exists()


@needs_git
def test_an_adopted_ref_is_reported_as_the_repositorys_own_and_not_as_a_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The summary's third arm, and the one the invariant needs: a workflow was planned, but from
    # the ref `keelline.toml` already recorded rather than from the pin this run resolved. Naming
    # the resolved release here would assert that the gate GitHub runs is that release's, which
    # is exactly what `doctor`'s `ci-ref` row would then report as red.
    from keelline import runner as runner_module

    root = _repo(tmp_path)
    recorded = "e" * 40
    (root / "keelline.toml").write_text(
        '[keelline]\nversion = "0.1.0"\n\n[project]\nname = "widget"\n\n'
        f'[ci]\nmode = "reusable"\nref = "{recorded}"\n',
        encoding="utf-8",
    )
    sha = "c" * 40
    monkeypatch.setattr(
        runner_module, "subprocess_runner", lambda: _Listing(f"{sha}\trefs/tags/v0.1.0\n")
    )
    # The dry run first, because it writes nothing and leaves the repository fresh for the real
    # one below: `--json` is where a caller reads which ref the workflow will carry.
    code, printed = _run(root, tmp_path, "--yes", "--dry-run", "--json")
    assert code == 0, printed
    data = json.loads(printed)
    assert data["ref"] == recorded and data["pin"] == {"tag": "v0.1.0", "sha": sha}
    code, plain = _run(root, tmp_path, "--yes")
    assert code == 0, plain
    assert "CI: the workflow pins the [ci] ref this repository already recorded" in plain
    assert f"v0.1.0@{sha}" not in plain
    workflow = (root / ".github" / "workflows" / "keelline.yml").read_text(encoding="utf-8")
    assert f"check.yml@{recorded}" in workflow and sha not in workflow


def _ci_config(mode: str, ref: str, tmp_path: Path) -> Config:
    text = (
        '[keelline]\nversion = "0.1.0"\n\n[project]\nname = "widget"\n\n'
        f'[ci]\nmode = "{mode}"\nref = "{ref}"\n'
    )
    return loads(text, tmp_path, machine=tmp_path / "absent.toml")


def test_the_ci_line_has_no_arm_no_run_can_reach(tmp_path: Path) -> None:
    """An unreachable branch is a vacuous assertion in another shape.

    `run_init` read `if skipped is not None or not report.ref:` and formatted
    `skipped or <a fallback>`, and neither the disjunct nor the fallback could ever fire.
    `templates._ci` returns a rendered workflow only for a `[ci] ref` that is non-empty and
    matches `CI_REF`, and a non-empty reason in every other arm; `init` then derives
    `report.ref` as `"" if "ci-workflow" in prepared.skipped else config.ci.ref` -- its own
    comment calls the two "one value by construction", and `doctor`'s `ci-ref` row enforces it.
    So a run with no skip has a ref, and a sentence nobody can provoke has been deleted rather
    than left standing as a claim about a state the code forbids.

    Both halves are asserted. The invariant is walked over `_ci`'s own arms, so this is a
    statement about the code rather than about one run; the source is read with its comments
    stripped, because what "unreachable" means here is that the arm is gone and no behaviour
    moved when it went.

    Mutation: `mutations.toml`'s "the init CI line grows an arm no run can reach".
    """
    code = "\n".join(
        line
        for line in inspect.getsource(run_init).splitlines()
        if not line.strip().startswith("#")
    )
    assert "no workflow was planned" not in code
    assert "not report.ref" not in code

    rendered, skipped = 0, 0
    for mode, ref, adopted in [
        ("none", "", False),
        ("uvx", "", False),
        ("reusable", "", True),
        ("reusable", "", False),
        ("reusable", "not-a-sha", False),
        ("reusable", "a" * 40, False),
    ]:
        config = _ci_config(mode, ref, tmp_path)
        workflow, reason = _ci(config, Resolution(None, True), adopted=adopted, dry_run=False)
        if workflow is not None:
            # The half the deleted arm rested on: a workflow is planned only for a ref, so
            # `init`'s `report.ref` cannot be empty while `ci-workflow` is absent from `skipped`.
            assert reason is None and config.ci.ref
            rendered += 1
        else:
            # And the other half: every skip carries a sentence, so the fallback had nothing to
            # stand in for either.
            assert reason
            skipped += 1
    # Non-vacuous: both branches were actually taken.
    assert rendered and skipped
