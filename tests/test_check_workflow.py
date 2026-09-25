"""`check.yml`'s one job, held to its shape and its two gate steps run as the scripts they are.

The repository carries no YAML parser, so the job is read as lines: its steps by the `- name:`
and `- uses:` lines at the steps' indentation, and each gate step's `run: |` body extracted from
the shipped file by `step_script` and run with `bash` in a workspace laid out as the runner lays
it out — the caller's checkout at `project/`, against a real clone, with the real `keelline gate`.
Only the two checkouts and `setup-python` are the platform's and are not run here; the base
step's own cases are in `tests/test_fixtures.py`.

**What the judging step must hold.** It is the step whose exit status is the verdict, so it runs
no command the repository wrote (`--builtin`) and imports nothing from the working directory
(`python3 -P`), it judges the configuration whatever `only:` names, and it may not fail quietly.
The project's own gates run in the next step, and only after it passed.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import keelline
from keelline.config.loader import CONFIG_FILE
from tests.assess.baserepo import clone, commit
from tests.gitfixture import git, needs_git
from tests.test_fixtures import CHECK_WORKFLOW, ROOT, needs_bash, needs_workflow, step_script

JUDGE = "The configuration and the built-in gates"
CUSTOM = "The project's own gates"
PROOF = "Keelline runs at all"
BASE_STEP = "The base ref and the project root"

BASE = f"""[keelline]
version = "{keelline.__version__}"
state = "adopting"
enforced = ["docs"]

[project]
name = "widget"
"""
LOOSENED = BASE.replace('["docs"]', "[]")
# Well past the preset's `AGENTS.md` budget, so the `docs` gate has a finding.
OVER_BUDGET = "".join("word\n" for _ in range(400))

# A step starts at a `- name:` or a `- uses:` line at the steps' indentation. A `uses:` step may
# carry a trailing `# vN`, which a reader anchored at `\S+$` refused, and so never counted
# `setup-python`: the walk's count is only a claim about the job if every spelling is read.
_STEP = re.compile(r"^      - (?:name: (?P<name>.+)|uses: (?P<uses>\S+)(?:\s+#.*)?)$")
_JOB = re.compile(r"^  ([a-z-]+):$", re.MULTILINE)
_IF = re.compile(r"^        if: (?P<condition>.+)$")


def _jobs_text() -> str:
    """The file from its `jobs:` key on, read at call time: the sdist carries no `.github/`."""
    text = CHECK_WORKFLOW.read_text(encoding="utf-8")
    return text[text.index("\njobs:\n") :]


def _steps() -> list[tuple[str, bool, str | None]]:
    """`(name, may it fail, its if: condition)` for each step of the job, in order."""
    steps: list[tuple[str, bool, str | None]] = []
    for line in _jobs_text().splitlines():
        match = _STEP.match(line)
        if match:
            steps.append((match.group("name") or match.group("uses"), False, None))
            continue
        if not steps:
            continue
        name, may_fail, condition = steps[-1]
        if line == "        continue-on-error: true":
            steps[-1] = (name, True, condition)
        elif (guard := _IF.match(line)) is not None:
            steps[-1] = (name, may_fail, guard.group("condition"))
    return steps


def _step_text(name: str) -> str:
    """Every line of the named step, from its `- name:` line to the next step's."""
    lines = _jobs_text().splitlines()
    start = lines.index(f"      - name: {name}")
    end = next(
        (i for i in range(start + 1, len(lines)) if _STEP.match(lines[i])),
        len(lines),
    )
    return "\n".join(lines[start:end]) + "\n"


def _clone(tmp_path: Path, base: str = BASE) -> tuple[Path, str]:
    """The runner's workspace, with the caller's checkout at `project/` on a branch `change`,
    and the base commit the base step would have resolved."""
    workspace = tmp_path / "workspace"
    clone(workspace, base)
    base_sha = git(workspace / "project", "rev-parse", "refs/remotes/origin/main").strip()
    return workspace, base_sha


def _commit(workspace: Path, path: str, text: str) -> None:
    project = workspace / "project"
    (project / path).write_text(text, encoding="utf-8")
    commit(project, "chore: the change under review")


def _judge(workspace: Path, base_sha: str, only: str, step: str = JUDGE) -> tuple[int, str, str]:
    """The named gate step, run as the runner runs it: from the workspace, with exactly the
    environment its `env:` block and the runner provide."""
    summary = workspace / "step-summary.md"
    summary.unlink(missing_ok=True)
    done = subprocess.run(
        ["bash", "-e", "-c", step_script(CHECK_WORKFLOW, step)],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
        env={
            # The interpreter running this suite stands in for `setup-python`'s: the step names
            # `python3`, and a system one below the floor would fail for a reason CI never meets.
            "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin:/usr/local/bin",
            "HOME": str(workspace),
            "PYTHONPATH": str(ROOT / "src"),
            "ROOT": "project/.",
            "BASE_SHA": base_sha,
            "WORKFLOW_SHA": "0" * 40,
            "ONLY": only,
            "GITHUB_STEP_SUMMARY": str(summary),
        },
    )
    written = summary.read_text(encoding="utf-8") if summary.exists() else ""
    return done.returncode, done.stdout + done.stderr, written


def _marker_gate(marker: Path) -> str:
    """A `[gates.custom.tests]` table whose command writes `marker`."""
    argv = json.dumps([Path(sys.executable).as_posix(), "-c", f"open({str(marker)!r}, 'w')"])
    return f"\n[gates.custom.tests]\nrun = {argv}\n"


@needs_workflow
def test_one_job_whose_judging_steps_may_not_fail_and_run_in_order() -> None:
    # The verdict is the job's status, so a step that may fail — `continue-on-error`, or an
    # `if:` that runs it after a failure or skips it — is a verdict that can be turned green.
    # `keelline gate` already exits 0 for an advisory gate's findings, so no step here needs
    # either. Mutations (declared): the judging step gains `continue-on-error: true`; the custom
    # step gains `if: always()`, which would run the repository's commands after a refusal.
    assert _JOB.findall(_jobs_text()) == ["gates"], _JOB.findall(_jobs_text())
    steps = _steps()
    names = [name for name, _, _ in steps]
    # The walk's count before anything is read off it: a reader that stopped matching one
    # spelling would drop a step, and every `index` below would still find the others.
    assert len(steps) == 8, steps
    assert any(name.startswith("actions/setup-python@") for name in names), names
    assert [(name, may_fail) for name, may_fail, _ in steps if may_fail] == [], steps
    assert [(name, condition) for name, _, condition in steps if condition] == [], steps
    # A Keelline that cannot run fails under its own name before anything reads as a finding,
    # the base is resolved before either gate step reads it, and the repository's own commands
    # run last.
    assert names.index(PROOF) < names.index(BASE_STEP) < names.index(JUDGE) < names.index(CUSTOM)
    assert names[-2:] == [JUDGE, CUSTOM], names


@needs_workflow
def test_both_gate_steps_start_python_without_the_working_directory_on_its_path() -> None:
    # Nothing the repository wrote may execute in the process that holds the verdict, and a
    # module the interpreter imports from its working directory is something the repository
    # wrote. The steps run from the workspace today, which the pull request writes nothing
    # into; `-P` keeps that true if a later edit gives a gate step `working-directory: project`,
    # as the base step it replaced had. And no step reads anything with `python3 -c` any more:
    # the base step that did is gone. Mutation (declared): `python3 -m` for `python3 -P -m` in
    # the judging step.
    for step in (JUDGE, CUSTOM):
        assert "python3 -P -m keelline gate" in step_script(CHECK_WORKFLOW, step), step
    assert "python3 -c" not in _jobs_text()


@needs_workflow
def test_the_judging_step_passes_the_platform_s_workflow_sha_through_env() -> None:
    # An upgrade's `[ci] ref` is admitted only at the commit the platform says is running, so
    # the judging step must hand `keelline gate` that commit, and from the platform's own record
    # — through `env:`, never spliced into the script. No clone case reaches an admitted move,
    # which needs a released tag, so the wiring is held here. Mutation (declared): drop
    # `--workflow-sha "$WORKFLOW_SHA"`.
    assert '--workflow-sha "$WORKFLOW_SHA"' in step_script(CHECK_WORKFLOW, JUDGE)
    assert "          WORKFLOW_SHA: ${{ job.workflow_sha }}\n" in _step_text(JUDGE)


@needs_git
@needs_bash
@needs_workflow
@pytest.mark.parametrize("only", ["config", ""])
def test_the_judging_step_fails_a_change_that_loosens_what_the_base_enforces(
    tmp_path: Path, only: str
) -> None:
    # The base enforces `docs` and the change empties `enforced`: a pull request turning off a
    # gate it is about to face. The step must fail, say which key in an error annotation, and
    # write it into the job summary. Mutations (declared): the step judges the tree against
    # itself; it stops annotating; it writes no job summary.
    workspace, base_sha = _clone(tmp_path)
    _commit(workspace, CONFIG_FILE, LOOSENED)
    code, printed, summary = _judge(workspace, base_sha, only)
    assert code == 1, printed
    assert "::error" in printed and "keelline.enforced" in printed, printed
    assert "keelline.enforced" in summary, summary


@needs_git
@needs_bash
@needs_workflow
def test_the_judging_step_judges_the_configuration_whatever_only_names(tmp_path: Path) -> None:
    # `only:` is the caller's, and the caller is pull-request content: a pull request that
    # loosens `enforced` and sets `only: docs` in its own caller would otherwise run the `docs`
    # gate under the base's configuration, pass it, and never meet the configuration check. So
    # the judging step asks for `config` whatever else `only:` names. Mutation (declared): the
    # step stops adding it.
    workspace, base_sha = _clone(tmp_path)
    _commit(workspace, CONFIG_FILE, LOOSENED)
    code, printed, summary = _judge(workspace, base_sha, "docs")
    assert code == 1, printed
    assert "keelline.enforced" in printed and "keelline.enforced" in summary, printed


@needs_git
@needs_bash
@needs_workflow
def test_only_runs_the_names_it_is_given_and_nothing_else(tmp_path: Path) -> None:
    # `AGENTS.md` over its budget under a base that enforces `docs`: only a run that includes
    # `docs` fails. `config` alone judges an unchanged configuration and passes, which is what a
    # matrix leg of its own is for. Mutation (declared): the loop that turns `only:` into
    # `--only` arguments is removed, so every leg runs every gate.
    workspace, base_sha = _clone(tmp_path)
    _commit(workspace, "AGENTS.md", OVER_BUDGET)
    code, printed, _ = _judge(workspace, base_sha, "config")
    assert code == 0, printed
    for only in ("", "config docs"):
        code, printed, _ = _judge(workspace, base_sha, only)
        assert code == 1, (only, printed)


@needs_git
@needs_bash
@needs_workflow
def test_an_only_name_is_never_expanded_as_a_file_pattern(tmp_path: Path) -> None:
    # `$ONLY` is split unquoted, which is also where the shell would glob: `d*` beside a file
    # called `docs` in the workspace would become the `docs` gate. With globbing off it stays
    # `d*`, a name no configuration has, and `keelline gate` refuses it (2). Mutation
    # (declared): `set -f` is removed.
    workspace, base_sha = _clone(tmp_path)
    (workspace / "docs").write_text("", encoding="utf-8")
    code, printed, _ = _judge(workspace, base_sha, "d*")
    assert code == 2, printed


@needs_git
@needs_bash
@needs_workflow
def test_the_judging_step_runs_no_custom_gate_and_the_next_step_runs_them(tmp_path: Path) -> None:
    # A custom gate executes files the pull request can change, so it must never run in the
    # process that decides the verdict. The next step runs it, once the judging step passed.
    # Mutation (declared): the judging step loses `--builtin` and the marker appears.
    workspace, base_sha = _clone(tmp_path)
    marker = tmp_path / "marker"
    _commit(workspace, CONFIG_FILE, BASE + _marker_gate(marker))
    code, printed, _ = _judge(workspace, base_sha, "")
    assert code == 0, printed
    assert not marker.exists(), printed
    code, printed, _ = _judge(workspace, base_sha, "", step=CUSTOM)
    assert code == 0, printed
    assert marker.exists(), printed
