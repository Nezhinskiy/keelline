"""`check.yml`'s one job, held to its shape and its two gate steps run as the scripts they are.

The repository carries no YAML parser, so the file is read by `tests.workflow_yaml`, one strict
reader that returns the whole document or fails naming the line it cannot read, and each gate
step's script is taken from it by `step_script` and run with `bash` in a workspace laid out as
the runner lays it out — the caller's checkout at `project/`, against a real clone, with the
real `keelline gate`. Only the two checkouts and `setup-python` are the platform's and are not
run here; the base step's own cases are in `tests/test_fixtures.py`.

**What the judging step must hold.** It is the step whose exit status is the verdict, so it runs
no command the repository wrote (`--builtin`) and imports nothing from the working directory or a
user site directory (`python3 -P -s`), it judges the configuration whatever `only:` names, and it
may not fail quietly. The project's own gates run in the next step, and only after it passed.
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
    step_script,
)
from tests.workflow_yaml import Node, load

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

# Every line that names an interpreter, whole, in the order the job runs them. Only three are
# Keelline's, and a whitelist rather than a list of bad spellings: `-c` with flags before it,
# `-Pc`, a program on standard input, a script path, an assignment in front of the command
# (`PYTHONUSERBASE=… python3 …`), a wrapper (`env`, `exec`) or a second command packed onto the
# line after a `;` are each a way the checkout reaches the interpreter, and a pattern for each
# is a pattern for the ones thought of. Whole lines and not a prefix, because a prefix is
# satisfied by a line that goes on to run something else.
_PYTHON = re.compile(r"\bpython[\d.]*\b")
KEELLINE_INVOCATIONS = (
    "python3 -m keelline --version",
    'python3 -P -s -m keelline gate --builtin --root "$ROOT" --base "$BASE_SHA" \\',
    'python3 -P -s -m keelline gate --custom --root "$ROOT" --base "$BASE_SHA" \\',
)
GATE_ENV: dict[str, Node] = {
    "PYTHONPATH": "keelline/src",
    "ROOT": "${{ steps.base.outputs.root }}",
    "BASE_SHA": "${{ steps.base.outputs.base_sha }}",
    "WORKFLOW_SHA": "${{ job.workflow_sha }}",
    "ONLY": "${{ inputs.only }}",
}
SCRIPT = "<script>"
# The job, every step whole but its script, in order; an action is named without its ref, so a
# pin moving is not a change here. Everything that reaches a step's process other than the
# platform's own variables is in this list: its `env:`, its working directory, its action's
# inputs, and whether it may fail or be skipped (a key the list does not carry).
STEPS: list[dict[str, Node]] = [
    {
        "name": "The caller's repository",
        "uses": "actions/checkout",
        "with": {"path": "project", "fetch-depth": "0", "persist-credentials": "false"},
    },
    {
        "name": "Keelline, at this workflow's own commit",
        "uses": "actions/checkout",
        "with": {
            "repository": "${{ job.workflow_repository }}",
            "ref": "${{ job.workflow_sha }}",
            "path": "keelline",
            "persist-credentials": "false",
        },
    },
    {
        "name": "The checkout is the commit this workflow file is at",
        "env": {"EXPECTED": "${{ job.workflow_sha }}"},
        "run": SCRIPT,
    },
    {"uses": "actions/setup-python", "with": {"python-version": "${{ inputs.python-version }}"}},
    {"name": PROOF, "env": {"PYTHONPATH": "keelline/src"}, "run": SCRIPT},
    {
        "name": BASE_STEP,
        "id": "base",
        "working-directory": "project",
        "env": {
            "INPUT_BASE": "${{ inputs.base }}",
            "INPUT_PATH": "${{ inputs.path }}",
            "PR_BASE": "${{ github.base_ref }}",
            "DEFAULT_BRANCH": "${{ github.event.repository.default_branch }}",
        },
        "run": SCRIPT,
    },
    {"name": JUDGE, "env": GATE_ENV, "run": SCRIPT},
    {"name": CUSTOM, "env": GATE_ENV, "run": SCRIPT},
]
# And each script's text, line for line, comments and blank lines aside: `STEPS` holds what a
# step is given, and this holds what it does with it. A line that is not an invocation can still
# change the verdict's process — `export PYTHONUSERBASE=…` or `. project/.ci-env` in a gate step,
# or a copy into `keelline/src/` from an earlier one, where the verdict's `PYTHONPATH` imports a
# `sitecustomize.py` at start-up — and every such line is a line this list does not carry.
CHECKOUT_STEP = "The checkout is the commit this workflow file is at"
SCRIPTS: dict[str, list[str]] = {
    CHECKOUT_STEP: [
        'actual="$(git -C keelline rev-parse HEAD)"',
        '[ "$actual" = "$EXPECTED" ] || { echo "::error::checked out $actual, not the workflow\'s'
        ' own $EXPECTED"; exit 1; }',
    ],
    PROOF: ["python3 -m keelline --version"],
    BASE_STEP: [
        'case "$INPUT_PATH" in',
        '  ""|.|./) p="" ;;',
        '  *) p="${INPUT_PATH#./}"; p="${p%/}" ;;',
        "esac",
        'case "$p" in',
        "  *[!A-Za-z0-9._/-]*)",
        "    echo \"::error::path: must be a plain relative path — letters, digits, '.', '_', '-'"
        " and '/'\"",
        "    exit 1",
        "    ;;",
        "  ..|../*|*/..|*/../*)",
        '    echo "::error::path: must not leave the checkout"',
        "    exit 1",
        "    ;;",
        "esac",
        'if [ -n "$PR_BASE" ] && [ -n "$INPUT_BASE" ] && [ "$INPUT_BASE" != "$PR_BASE" ]; then',
        "  echo \"::error::base: names another branch, but this pull request's base is"
        " '$PR_BASE'; the gates' configuration is read from the base the platform reports\"",
        "  exit 1",
        "fi",
        'base="$INPUT_BASE"',
        '[ -n "$base" ] || base="$PR_BASE"',
        '[ -n "$base" ] || base="$DEFAULT_BRANCH"',
        '[ -n "$base" ] || { echo "::error::no base ref: pass \'base:\'"; exit 1; }',
        'git check-ref-format --branch "$base" >/dev/null',
        'base_sha="$(git rev-parse --verify --quiet "refs/remotes/origin/$base^{commit}")" ||',
        '  { echo "::error::origin/$base is not in this checkout — check out with fetch-depth: 0,'
        ' or name a base that exists"; exit 1; }',
        "{",
        '  echo "base_sha=$base_sha"',
        '  echo "root=project/${p:-.}"',
        '} >> "$GITHUB_OUTPUT"',
    ],
    JUDGE: [
        "set -f",
        "only=()",
        'for name in $ONLY; do only+=("--only=$name"); done',
        "set +f",
        'if [ "${#only[@]}" -gt 0 ]; then only+=("--only=config"); fi',
        KEELLINE_INVOCATIONS[1],
        '  --workflow-sha "$WORKFLOW_SHA" --annotate --summary "$GITHUB_STEP_SUMMARY" "${only[@]}"',
    ],
    CUSTOM: [
        "set -o noglob",
        "custom=()",
        'for name in $ONLY; do custom+=("--only=$name"); done',
        "set +o noglob",
        KEELLINE_INVOCATIONS[2],
        '  --workflow-sha "$WORKFLOW_SHA" --annotate --summary "$GITHUB_STEP_SUMMARY"'
        ' "${custom[@]}"',
    ],
}


def _workflow() -> dict[str, Node]:
    """`check.yml`, read at call time (the sdist carries no `.github/`) by the strict reader."""
    document = load(CHECK_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict), document
    return document


def _job() -> dict[str, Node]:
    jobs = _workflow()["jobs"]
    assert isinstance(jobs, dict) and list(jobs) == ["gates"], jobs
    job = jobs["gates"]
    assert isinstance(job, dict), job
    return job


def _steps() -> list[dict[str, Node]]:
    steps = _job()["steps"]
    assert isinstance(steps, list) and all(isinstance(step, dict) for step in steps), steps
    return [step for step in steps if isinstance(step, dict)]


def _name(step: dict[str, Node]) -> str:
    name = step.get("name") or step.get("uses")
    assert isinstance(name, str), step
    return name.split("@")[0]


def _step(name: str) -> dict[str, Node]:
    return next(step for step in _steps() if _name(step) == name)


def _shape(step: dict[str, Node]) -> dict[str, Node]:
    """The step without its script's text and its action's ref."""
    shaped: dict[str, Node] = {}
    for key, value in step.items():
        if key == "run":
            shaped[key] = SCRIPT
        elif key == "uses" and isinstance(value, str):
            shaped[key] = value.split("@")[0]
        else:
            shaped[key] = value
    return shaped


def _scripts() -> list[str]:
    return [step["run"] for step in _steps() if isinstance(step.get("run"), str)]  # type: ignore[misc]


def _commands(script: str) -> list[str]:
    """The script's lines, less its blank lines and comment lines — except one that follows a
    line continued with `\\`, because there bash ends the command the line above says goes on,
    and the lines after it run as a command of their own."""
    kept: list[str] = []
    previous = ""
    for line in script.splitlines():
        bare = line.strip()
        if (bare and not bare.startswith("#")) or previous.endswith("\\"):
            kept.append(line)
        previous = line
    return kept


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
    """The named step's `env:` block, as the strict reader reads it: every key, a comment or a
    blank line anywhere in it notwithstanding, and a key written twice refused."""
    env = _step(step).get("env")
    assert isinstance(env, dict) and all(isinstance(v, str) for v in env.values()), env
    return {key: value for key, value in env.items() if isinstance(value, str)}


def _judge(
    workspace: Path,
    base_sha: str,
    only: str,
    step: str = JUDGE,
    *,
    interpreter: Path | None = None,
    extra: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """The named gate step, run as the runner runs it: from the workspace, with the environment
    its own `env:` block names and the runner's few variables, and nothing else — unless a case
    passes `extra`, a variable the step's `env:` could name, or `interpreter`, the directory
    whose `python3` stands in for `setup-python`'s.

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
            "PATH": f"{interpreter or Path(sys.executable).parent}:/usr/bin:/bin:/usr/local/bin",
            "HOME": str(workspace),
            "GITHUB_STEP_SUMMARY": str(summary),
            **named,
            **(extra or {}),
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
    job = _job()
    # And the job itself carries neither: an `if:` on `gates` skips it, and a skipped job is a
    # required check the platform reports as passing. So the job's keys are held whole, which
    # also keeps a job-level `env:` from reaching every step. Mutation (declared): the job gains
    # an `if:`.
    assert list(job) == ["runs-on", "timeout-minutes", "defaults", "steps"], list(job)
    steps = _steps()
    names = [_name(step) for step in steps]
    # Every step's keys, whole and in order: a step that may fail or may be skipped carries a
    # key the list does not, and a step with no name is a ninth step. Mutation (declared): such
    # a step before the proof step.
    found = [(_name(step), list(step)) for step in steps]
    assert found == [(_name(step), list(step)) for step in STEPS], found
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
    # the base step that did is gone. `-s` is the user site's half, and its behaviour is the
    # `.pth` case below. Mutations (declared): `python3 -s -m` for `python3 -P -s -m` in the
    # judging step, and in the custom step.
    for step in (JUDGE, CUSTOM):
        assert "python3 -P -s -m keelline gate" in step_script(CHECK_WORKFLOW, step), step
    # And no interpreter the job starts runs anything but Keelline, in any spelling: every
    # line that names one, comments aside, is one of Keelline's three invocation lines, whole
    # and in order. Mutations (declared): the proof step runs `python3 -P -c`, `python3 -Pc`, or
    # a program on standard input; the judging step's command gains an assignment in front of
    # it. Whole, because `… gate --help >/dev/null; PYTHONUSERBASE=… python3 -P -m keelline gate
    # --builtin …`, written before `-s`, began with an invocation and passed a prefix match.
    # Mutation (declared): the judging step's command line runs a second command before the gate.
    invocations = [
        line.strip()
        for script in _scripts()
        for line in script.splitlines()
        if not line.strip().startswith("#") and _PYTHON.search(line)
    ]
    assert invocations == list(KEELLINE_INVOCATIONS), invocations


@needs_workflow
def test_the_judging_step_passes_the_platform_s_workflow_sha_through_env() -> None:
    # An upgrade's `[ci] ref` is admitted only at the commit the platform says is running, so
    # the judging step must hand `keelline gate` that commit, and from the platform's own record
    # — through `env:`, never spliced into the script. No clone case reaches an admitted move,
    # which needs a released tag, so the wiring is held here. Mutation (declared): drop
    # `--workflow-sha "$WORKFLOW_SHA"`.
    assert '--workflow-sha "$WORKFLOW_SHA"' in step_script(CHECK_WORKFLOW, JUDGE)
    assert _step_env(JUDGE)["WORKFLOW_SHA"] == "${{ job.workflow_sha }}"


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
    """Everything that reaches a step's process, held whole for every step, because `-P -s`
    cover only the working directory and the user site directory: a `PYTHONPATH` entry inside the
    checkout, a `PYTHONSTARTUP`, a `working-directory: project`, or a `BASH_ENV` the step's
    non-interactive bash sources would each hand the pull request code in the process that
    decides the verdict — or, in an earlier step, code that writes `$GITHUB_ENV` or
    `$GITHUB_PATH` and so chooses the next steps' environment and interpreter.

    What reaches it: the workflow's keys (no `env:`), the job's (no `env:`, no `if:`), the job's
    `defaults:` (the shell and nothing else), and each step whole but for its script's text —
    `env:`, `with:`, `working-directory:` and every other key — read by the strict reader, so a
    comment or a blank line inside a block hides nothing, and a key written twice is refused.
    No script writes `$GITHUB_ENV` or `$GITHUB_PATH` at all, and the next case holds every
    script's text. The runner's own variables and the `PATH` `setup-python` extends are the
    platform's.
    """
    workflow = _workflow()
    assert list(workflow) == ["name", "on", "permissions", "jobs"], list(workflow)
    assert _job()["defaults"] == {"run": {"shell": "bash"}}, _job()["defaults"]
    assert [_shape(step) for step in _steps()] == STEPS, [_shape(step) for step in _steps()]
    # Mutation (declared): the base step appends to `$GITHUB_ENV`.
    assert [s for s in _scripts() if "GITHUB_ENV" in s or "GITHUB_PATH" in s] == []


@needs_workflow
def test_the_job_s_token_can_read_the_repository_and_nothing_more() -> None:
    # Every step runs with the job's token in reach of the platform, the project's own gates
    # included, and those execute files the pull request can change. The checkouts need to read
    # the repository and nothing else, so that is all the workflow grants; the workflow's keys
    # above hold that `permissions:` is there, and this holds what it says. The job carries no
    # `permissions:` of its own, which the job's keys hold. Mutation (declared): `contents:
    # write`.
    permissions = _workflow()["permissions"]
    assert permissions == {"contents": "read"}, permissions


@needs_workflow
def test_every_script_the_job_runs_is_held_line_for_line() -> None:
    """The class the environment case above leaves open: a script line that changes the
    verdict's process — its environment or the code it imports — without being an invocation.

    `-P` keeps the working directory off `sys.path` and nothing more. Measured with a
    `setup-python`-shaped interpreter (not a virtual environment), before the gate steps passed
    `-s`: a `.pth` under `project/.local` ran at start-up once the step exported
    `PYTHONUSERBASE=project/.local`, and a `sitecustomize.py` copied into `keelline/src/` ran at
    start-up under the step's own `PYTHONPATH`. `-s` answers the first, and nothing but this
    hold answers the second. `export`, `.`/`source`, `cd`, `eval`, `umask` and a write into either
    checkout are each one line, and a list of forbidden spellings is a list of the ones thought
    of; so every script is held whole, comments aside, and a line the list does not carry reddens
    here.
    Mutations (declared): the judging step exports `PYTHONUSERBASE`; the custom step sources a
    file from the caller's checkout; the base step copies a file into Keelline's checkout.
    """
    found = {_name(step): _commands(str(step["run"])) for step in _steps() if "run" in step}
    assert found == SCRIPTS, found


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


def _outside_any_virtual_environment(tmp_path: Path) -> Path:
    """A directory whose `python3` is this suite's interpreter outside its virtual environment.

    A virtual environment turns the user site directory off by itself, so the suite's own
    interpreter would pass a case about the user site whatever flags the step passed. The
    interpreter `setup-python` installs is not in one, and neither is this.
    """
    directory = tmp_path / "bin"
    directory.mkdir()
    # Not typed in the standard library's stubs; the case below asserts it is what it says.
    (directory / "python3").symlink_to(Path(getattr(sys, "_base_executable", sys.executable)))
    return directory


@needs_git
@needs_bash
@needs_workflow
@pytest.mark.parametrize("step", [JUDGE, CUSTOM], ids=["judging", "custom"])
def test_no_pth_file_under_a_user_base_in_the_checkout_runs_in_a_gate_step(
    tmp_path: Path, step: str
) -> None:
    # `-P` leaves the user site directory on, and a `.pth` file in it runs at the interpreter's
    # start-up, before anything Keelline imports. The step's `env:` is held whole and names no
    # `PYTHONUSERBASE`; `-s` is what keeps a `.pth` the pull request commits out of the verdict's
    # process if it ever does. Measured before `-s`: with `PYTHONUSERBASE=project/.local`, a
    # committed `.pth` ran under `python3 -P`. Mutations (declared): `-s` dropped from the
    # judging step, and from the custom step.
    workspace, base_sha = _clone(tmp_path)
    marker = tmp_path / "planted"
    interpreter = _outside_any_virtual_environment(tmp_path)
    python3 = str(interpreter / "python3")
    user_base = {"PYTHONUSERBASE": "project/.local"}
    env = {"PATH": f"{interpreter}:/usr/bin:/bin:/usr/local/bin", "HOME": str(workspace)}
    site = subprocess.run(
        [python3, "-c", "import site; print(site.getusersitepackages())"],
        cwd=workspace,
        env={**env, **user_base},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    planted = workspace / site / "planted.pth"
    planted.parent.mkdir(parents=True)
    planted.write_text(f"import os; open({str(marker)!r}, 'w').close()\n", encoding="utf-8")
    commit(workspace / "project", "chore: a user base inside the checkout")
    # The case can fail: this interpreter, started without `-s`, runs the file.
    subprocess.run(
        [python3, "-P", "-c", "pass"], cwd=workspace, env={**env, **user_base}, check=True
    )
    assert marker.exists(), "no user site directory is read here, so nothing below could fail"
    marker.unlink()
    code, printed, _ = _judge(
        workspace, base_sha, "", step=step, interpreter=interpreter, extra=user_base
    )
    # The marker first: a `.pth` that ran is the finding, whatever the step then said.
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
