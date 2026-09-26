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
from tests.test_fixtures import (
    CHECK_WORKFLOW,
    ROOT,
    needs_bash,
    needs_workflow,
    run_blocks,
    step_script,
)

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
# A plain mapping key at the start of a line; `_keys` says what a line that is not one means.
_KEY_LINE = re.compile(r"^ *(?P<key>[a-z-]+):(?: |$)")
_ENV_ENTRY = re.compile(r"^          (?P<key>[A-Z_]+): (?P<value>.+)$")
# Every interpreter the job starts, and what follows it on the line. Only two invocations are
# Keelline's, and a whitelist rather than a list of bad spellings: `-c` with flags before it,
# `-Pc`, a program on standard input (`python3 -`, a heredoc, a pipe) and a script path are each
# a program the working directory can reach, and a pattern for each is a pattern for the ones
# thought of.
_PYTHON = re.compile(r"\bpython[\d.]*\b(?P<rest>[^\n]*)")
KEELLINE_INVOCATIONS = (" -m keelline --version", " -P -m keelline gate ")
# Each step's keys past its dash line, in order: what may reach each step is its keys, so a key
# added to any step — `if:`, `continue-on-error:`, `shell:`, `working-directory:` — reddens.
STEP_KEYS = [
    ("The caller's repository", ["uses", "with"]),
    ("Keelline, at this workflow's own commit", ["uses", "with"]),
    ("The checkout is the commit this workflow file is at", ["env", "run"]),
    ("actions/setup-python", ["with"]),
    (PROOF, ["env", "run"]),
    (BASE_STEP, ["id", "working-directory", "env", "run"]),
    (JUDGE, ["env", "run"]),
    (CUSTOM, ["env", "run"]),
]


def _jobs_text() -> str:
    """The file from its `jobs:` key on, read at call time: the sdist carries no `.github/`."""
    text = CHECK_WORKFLOW.read_text(encoding="utf-8")
    return text[text.index("\njobs:\n") :]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _meaningful(line: str) -> bool:
    """Neither blank nor a comment: a line YAML reads as content."""
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _keys(text: str, indent: int) -> list[str]:
    """Every key at exactly `indent` spaces in `text`, in order.

    A line at that indentation that is content and not a plain key — a quoted key, a flow
    mapping, a list item — fails here instead of being skipped: a line reader that passes over
    what it cannot read reports clean over exactly that line.
    """
    keys: list[str] = []
    for line in text.splitlines():
        if not _meaningful(line) or _indent(line) != indent:
            continue
        match = _KEY_LINE.match(line)
        assert match is not None, f"not a plain key at {indent} spaces: {line!r}"
        keys.append(match.group("key"))
    return keys


def _steps() -> list[tuple[str, str]]:
    """`(name, text)` for each step of the job, in order; a `uses:` step with no name is named
    by its action, without the ref.

    Every line from `steps:` to the end of the file belongs to a step, and a content line that
    is neither a step's dash line nor indented past it fails here: a step spelled `- run:` or
    `- id:` would otherwise be read as lines of the step above it, and the walk would count
    eight steps over nine.
    """
    text = _jobs_text()
    marker = "\n    steps:\n"
    steps: list[tuple[str, list[str]]] = []
    for line in text[text.index(marker) + len(marker) :].splitlines():
        match = _STEP.match(line)
        if match is not None:
            name = match.group("name") or match.group("uses").split("@")[0]
            steps.append((name, [line]))
            continue
        if not _meaningful(line):
            if steps:
                steps[-1][1].append(line)
            continue
        assert steps and _indent(line) >= 8, f"a line no step owns: {line!r}"
        steps[-1][1].append(line)
    return [(name, "\n".join(lines) + "\n") for name, lines in steps]


def _step_text(name: str) -> str:
    """Every line of the named step, from its dash line to the next step's."""
    return dict(_steps())[name]


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


def _step_env(step: str) -> dict[str, str]:
    """The named step's `env:` block, as written: each key and its value's text.

    The block is every line indented past the `env:` key, up to the next line that is not, as
    YAML reads it; and every one of those lines must be an entry. A reader that stopped at the
    first line it could not parse — a comment, a blank line, a key with a digit in it — left
    every key after that line out of the equality that holds the block, and out of the
    environment the cases run the step under.
    """
    lines = _step_text(step).splitlines()
    start = lines.index("        env:") + 1
    owned: list[str] = []
    for line in lines[start:]:
        if line.strip() and _indent(line) <= 8:
            break
        owned.append(line)
    assert [line for line in owned if not _ENV_ENTRY.match(line)] == [], owned
    return {
        match.group("key"): match.group("value")
        for match in (_ENV_ENTRY.match(line) for line in owned)
        if match is not None
    }


def _judge(workspace: Path, base_sha: str, only: str, step: str = JUDGE) -> tuple[int, str, str]:
    """The named gate step, run as the runner runs it: from the workspace, with the environment
    its own `env:` block names and the runner's few variables, and nothing else.

    The `env:` block is read off the shipped file rather than retyped here, so a value it gains
    — a `PYTHONPATH` that reaches into the checkout, say — is a value these cases run under.
    Each `${{ }}` in it is replaced by what the runner would put there in this case, and one this
    reader does not know is a failure rather than a guess. Keelline's own checkout is where the
    runner puts it, `keelline/` beside `project/`.
    """
    runner = {
        "${{ steps.base.outputs.root }}": "project/.",
        "${{ steps.base.outputs.base_sha }}": base_sha,
        "${{ job.workflow_sha }}": "0" * 40,
        "${{ inputs.only }}": only,
    }
    named = {
        key: runner[value] if value.startswith("${{") else value
        for key, value in _step_env(step).items()
    }
    checkout = workspace / "keelline"
    if not checkout.exists():
        checkout.symlink_to(ROOT, target_is_directory=True)
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
            "GITHUB_STEP_SUMMARY": str(summary),
            **named,
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
    assert _keys(_jobs_text(), 2) == ["gates"], _keys(_jobs_text(), 2)
    # And the job itself carries neither: an `if:` on `gates` skips it, and a skipped job is a
    # required check the platform reports as passing. So the job's keys are held whole, which
    # also keeps a job-level `env:` from reaching every step. Mutation (declared): the job gains
    # an `if:`.
    assert _keys(_jobs_text(), 4) == ["runs-on", "timeout-minutes", "defaults", "steps"]
    steps = _steps()
    names = [name for name, _ in steps]
    # Every step's keys, whole, in order: a step that may fail or may be skipped carries a key
    # the list does not, and a step spelled `- run:` with no name is a line no step owns, which
    # the walk refuses rather than fold into the step above it. Mutation (declared): such a step
    # before the proof step.
    found = [(name, _keys(text, 8)) for name, text in steps]
    assert found == STEP_KEYS, found
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
    # And no interpreter the job starts runs anything but Keelline, in any spelling: every
    # invocation in every script, comments aside, is one of Keelline's two. Mutations (declared):
    # the proof step runs `python3 -P -c`, `python3 -Pc`, or a program on standard input.
    invocations = [
        match.group("rest")
        for block in run_blocks(CHECK_WORKFLOW)
        for line in block.splitlines()
        if _meaningful(line)
        for match in _PYTHON.finditer(line)
    ]
    assert len(invocations) == 3, invocations
    assert [
        rest
        for rest in invocations
        if rest != KEELLINE_INVOCATIONS[0] and not rest.startswith(KEELLINE_INVOCATIONS[1])
    ] == [], invocations


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


@needs_workflow
def test_the_verdict_s_process_gets_only_the_environment_its_step_names() -> None:
    """Everything that reaches a gate step's process, held whole, because `-P` covers only the
    working directory: a `PYTHONPATH` entry inside the checkout, a `PYTHONSTARTUP`, a
    `working-directory: project` or an `env:` one level up would each hand the pull request a
    module in the process that decides the verdict.

    What reaches it: the workflow's and the job's own keys (neither may carry an `env:`), the
    job's `defaults:` (the shell and nothing else), the step's own keys (`env:` and `run:`, so no
    `working-directory:` and no `shell:`), the step's `env:` block (exactly these five, with
    `PYTHONPATH` naming Keelline's checkout alone), and `setup-python`'s inputs (the version and
    nothing that reads a file from the checkout). The runner's own variables and the `PATH`
    `setup-python` extends are the platform's; no step before these runs anything the pull
    request wrote, which the step walk above holds.
    """
    text = CHECK_WORKFLOW.read_text(encoding="utf-8")
    assert _keys(text, 0) == ["name", "on", "permissions", "jobs"], _keys(text, 0)
    assert "    defaults:\n      run:\n        shell: bash\n    steps:\n" in _jobs_text()
    for step in (JUDGE, CUSTOM):
        assert _keys(_step_text(step), 8) == ["env", "run"], step
        assert _step_env(step) == {
            "PYTHONPATH": "keelline/src",
            "ROOT": "${{ steps.base.outputs.root }}",
            "BASE_SHA": "${{ steps.base.outputs.base_sha }}",
            "WORKFLOW_SHA": "${{ job.workflow_sha }}",
            "ONLY": "${{ inputs.only }}",
        }, step
    setup = _step_text("actions/setup-python")
    assert _keys(setup, 10) == ["python-version"], setup
    assert "          python-version: ${{ inputs.python-version }}\n" in setup, setup


@needs_git
@needs_bash
@needs_workflow
@pytest.mark.parametrize("step", [JUDGE, CUSTOM], ids=["judging", "custom"])
def test_no_module_the_checkout_carries_is_imported_by_a_gate_step(
    tmp_path: Path, step: str
) -> None:
    # The behaviour the text above is about, run under the step's own `env:`: a pull request
    # that adds a `tomllib.py` at its top, which Keelline's loader would import in place of the
    # standard library's if the checkout were on `sys.path`. Measured when this case was
    # written: with `PYTHONPATH: keelline/src:project` the planted module ran, and one that
    # re-exported the real `tomllib` left the step at exit 0. Mutations (declared): that
    # `PYTHONPATH` on the judging step, and on the custom step.
    workspace, base_sha = _clone(tmp_path)
    marker = tmp_path / "planted"
    _commit(workspace, "tomllib.py", f"open({str(marker)!r}, 'w').close()\n")
    code, printed, _ = _judge(workspace, base_sha, "", step=step)
    # The marker first: a planted module that ran is the finding, whatever it then broke.
    assert not marker.exists(), printed
    assert code == 0, printed


@needs_git
@needs_bash
@needs_workflow
def test_the_custom_step_runs_only_the_custom_gates_only_names(tmp_path: Path) -> None:
    # A matrix leg's `only:` reaches the custom step too, so a leg named for a built-in gate
    # does not also run every command `[gates.custom]` names, and a leg named for a custom gate
    # runs that one. Mutation (declared): the custom step's loop is removed, and the `docs` leg
    # runs the marker gate.
    workspace, base_sha = _clone(tmp_path)
    marker = tmp_path / "marker"
    _commit(workspace, CONFIG_FILE, BASE + _marker_gate(marker))
    code, printed, _ = _judge(workspace, base_sha, "docs", step=CUSTOM)
    assert code == 0, printed
    assert not marker.exists(), printed
    code, printed, _ = _judge(workspace, base_sha, "tests", step=CUSTOM)
    assert code == 0, printed
    assert marker.exists(), printed
