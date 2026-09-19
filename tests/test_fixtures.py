"""The two fixture projects the smoke workflow runs against, held to what they claim.

`smoke-project` is a project every gate passes on, with `state = "installed"` so the gates
enforce; `hostile-project` (Task 15) is the S10 clone. Both are read by CI from this tree,
so a fixture that drifted from what a gate accepts would fail the smoke workflow with a
message about the fixture rather than about Keelline.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "tests" / "fixtures" / "smoke-project"
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
PLAN = "docs/plans/2026-09-19-the-fixtures-own-plan.md"


def _copy_as_repository(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(SMOKE, root)
    env = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "PATH": "/usr/bin:/bin",
    }

    # Two commits, so that `commit check --range HEAD~1..HEAD` checks one message rather than
    # an empty range that proves nothing. The second one touches the fixture's own plan rather
    # than being empty, for the same reason one step further on: `plan check --base HEAD~1`
    # lints the plans that range touches, and a range that touches none exits 0 having linted
    # nothing. `test_plan_check_on_the_fixture_lints_the_plan_it_touched` is what says so.
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)

    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "chore: the fixture")
    plan = root / PLAN
    added = plan.read_text(encoding="utf-8") + "\nA line the second commit adds.\n"
    plan.write_text(added, encoding="utf-8")
    git("add", "-A")
    git("-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "docs: a second one")
    return root


def _invoke(root: Path, tmp_path: Path, argv: list[str]) -> tuple[int, str]:
    parser = build_parser(discover_registrars())
    flags = ["--root", str(root), "--machine", str(tmp_path / "m.toml")]
    with redirect_stdout(io.StringIO()) as out:
        code = run([*argv, *flags], parser=parser)
    return code, out.getvalue()


@needs_git
@pytest.mark.parametrize(
    "argv",
    [
        ["docs", "check"],
        ["bugs", "check"],
        ["docs", "trail", "--check"],
        ["plan", "check", "--base", "HEAD~1"],
        ["commit", "check", "--range", "HEAD~1..HEAD"],
    ],
    ids=lambda argv: " ".join(argv),
)
def test_every_gate_the_workflow_runs_passes_on_the_smoke_fixture(
    tmp_path: Path, argv: list[str]
) -> None:
    # Mutation: delete `docs/roadmap.md`'s trail marker in the fixture -> `docs trail --check`
    # reddens (measured by hand, not declared: the fixture is data and the oracle mutates
    # source).
    #
    # `--base HEAD~1` and not the default: `plan check` defaults to `origin/<base_branch>`, and
    # this copy is a fresh repository with no remote, where an unresolvable base is a finding
    # (`docs/cli.md`: "A base that does not resolve is a finding (1), never an OK"). CI passes
    # `origin/<base>` and has one; the fixture's own two commits are the equivalent here.
    root = _copy_as_repository(tmp_path)
    code, printed = _invoke(root, tmp_path, argv)
    assert code == 0, printed


@needs_git
def test_plan_check_on_the_fixture_lints_the_plan_it_touched(tmp_path: Path) -> None:
    # The non-vacuity guard for the `plan check` row above, and the reason the fixture's second
    # commit is not empty: `plan check` over a range that touches no plan exits 0 having linted
    # nothing, which is the shape `plans.py`'s own docstring calls "how a gate like this one
    # runs green for its whole life". One plan, named, is what the row is worth.
    root = _copy_as_repository(tmp_path)
    code, printed = _invoke(root, tmp_path, ["plan", "check", "--base", "HEAD~1", "--json"])
    assert code == 0, printed
    assert PLAN in printed, printed


def test_the_smoke_fixture_is_installed_so_the_gates_enforce() -> None:
    import tomllib

    config = tomllib.loads((SMOKE / "keelline.toml").read_text(encoding="utf-8"))
    assert config["keelline"]["state"] == "installed"
    assert config["project"]["name"] == "smoke"


# --- `check.yml`'s base-ref step, run as the shell script it is -------------------------
#
# The repository carries no YAML parser and this plan adds no dependency to check its own
# prose, so a workflow is otherwise proven only by the run that first executes it. The one
# part of `check.yml` that is *logic* rather than platform plumbing is the step that decides
# which base ref the gate's configuration comes from and whether the run enforces. That step's
# `run:` body is extracted from the shipped file — never retyped here, or the test would hold
# a copy and the file would be free to drift — and run with `bash` against real repositories.

CHECK_WORKFLOW = ROOT / ".github" / "workflows" / "check.yml"
BASE_STEP = "The base ref, and the configuration it carries"
needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")
# `.github/` is outside `source-include`: it is this repository's own continuous integration
# and not source a downstream packager needs, and `scripts/check_artifacts.py` states that the
# sdist exists so such a packager can run the suite. So these five cases skip where the file
# they are about is not there, rather than the tree gaining a line to ship CI configuration.
needs_workflow = pytest.mark.skipif(
    not CHECK_WORKFLOW.is_file(), reason="check.yml is not in the sdist"
)


WORKFLOWS = ROOT / ".github" / "workflows"


def run_blocks(workflow: Path) -> list[str]:
    """Every `run:` value in the file, block scalar or one-liner, as text."""
    lines = workflow.read_text(encoding="utf-8").splitlines()
    found: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        index += 1
        if not stripped.startswith("run:"):
            continue
        rest = stripped[len("run:") :].strip()
        if not rest.startswith("|"):
            found.append(rest)
            continue
        indent = len(line) - len(line.lstrip())
        block: list[str] = []
        while index < len(lines):
            following = lines[index]
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            block.append(following)
            index += 1
        found.append("\n".join(block))
    return found


@needs_workflow
def test_no_workflow_splices_an_expression_into_a_shell() -> None:
    # The one class of workflow defect a text scan can catch, and the one worth catching: a
    # `${{ }}` inside a `run:` is interpolated by the platform before the shell sees the script,
    # so a ref name, a branch name or a pull-request title that carries shell metacharacters
    # runs as the workflow's own code. Every value in these files reaches a shell through
    # `env:` instead. The walk asserts it read something first, and something from each file.
    workflows = sorted(WORKFLOWS.glob("*.yml"))
    assert {p.name for p in workflows} >= {"ci.yml", "check.yml", "release.yml"}, workflows
    for workflow in workflows:
        blocks = run_blocks(workflow)
        assert blocks, workflow
        for block in blocks:
            assert "${{" not in block, (workflow.name, block)


def step_script(workflow: Path, step_name: str) -> str:
    """The `run: |` block of the named step, dedented, straight out of the shipped file."""
    lines = workflow.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == f"- name: {step_name}")
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    body = lines[run + 1 :]
    indent = len(body[0]) - len(body[0].lstrip())
    collected: list[str] = []
    for line in body:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        collected.append(line[indent:] if line.strip() else "")
    # No `${{ }}` may survive into the script: every value the step uses arrives through
    # `env:`, and one spliced into `run:` would be a command injection the test would run.
    assert "${{" not in "\n".join(collected), collected
    return "\n".join(collected) + "\n"


def _project_with_a_base(tmp_path: Path, *, on_base: str | None) -> Path:
    """A clone whose `origin/main` carries `on_base` as `keelline.toml`, or carries none."""
    env = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "PATH": "/usr/bin:/bin",
    }

    def git(where: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(where), *args], check=True, capture_output=True, env=env)

    upstream = tmp_path / "upstream"
    upstream.mkdir()
    git(upstream, "init", "-q", "-b", "main")
    (upstream / "README.md").write_text("# a project\n", encoding="utf-8")
    if on_base is not None:
        (upstream / "keelline.toml").write_text(on_base, encoding="utf-8")
    git(upstream, "add", "-A")
    git(upstream, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "chore: base")
    project = tmp_path / "project"
    clone = ["git", "clone", "-q", str(upstream), str(project)]
    subprocess.run(clone, check=True, capture_output=True, env=env)
    return project


def _run_base_step(
    project: Path, tmp_path: Path, **environment: str
) -> tuple[int, dict[str, str], str]:
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    done = subprocess.run(
        ["bash", "-e", "-c", step_script(CHECK_WORKFLOW, BASE_STEP)],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
        env={
            # The step reads the base's `keelline.toml` with `python3 -c "import tomllib"`, and
            # `tomllib` arrived in 3.11 — the floor this project sets and the version
            # `setup-python` installs on the runner. A system `python3` older than that would
            # fail the step here for a reason the workflow will never meet, so the interpreter
            # running this suite goes first on the PATH.
            "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin:/usr/local/bin",
            "GITHUB_OUTPUT": str(output),
            "INPUT_BASE": "",
            "INPUT_PATH": ".",
            "PR_BASE": "",
            "DEFAULT_BRANCH": "",
            "CURRENT_REF": "refs/pull/7/merge",
            **environment,
        },
    )
    emitted = output.read_text(encoding="utf-8").splitlines()
    written = dict(line.split("=", 1) for line in emitted if "=" in line)
    return done.returncode, written, done.stdout + done.stderr


INSTALLED = '[keelline]\nversion = "0.1.0"\nstate = "installed"\n\n[project]\nname = "p"\n'


@needs_git
@needs_bash
@needs_workflow
def test_a_base_branch_with_no_configuration_is_advisory_and_not_refused(tmp_path: Path) -> None:
    # D8's bootstrap: a project adopting the gate has no `keelline.toml` on its base branch
    # yet, and the run that would add one must not be the run that refuses it. `absent` is a
    # named state and not a fall-through — the fall-through is what `initialised` would be.
    project = _project_with_a_base(tmp_path, on_base=None)
    code, written, printed = _run_base_step(project, tmp_path, INPUT_BASE="main")
    assert code == 0, printed
    assert written["state"] == "absent", written
    assert written["enforce"] == "false", written
    assert written["base"] == "main"
    assert written["root"] == "project/."


@needs_git
@needs_bash
@needs_workflow
def test_an_installed_base_enforces(tmp_path: Path) -> None:
    project = _project_with_a_base(tmp_path, on_base=INSTALLED)
    code, written, printed = _run_base_step(project, tmp_path, INPUT_BASE="main")
    assert code == 0, printed
    assert written["state"] == "installed", written
    assert written["enforce"] == "true", written


@needs_git
@needs_bash
@needs_workflow
def test_a_branch_that_changes_an_installed_projects_configuration_is_refused(
    tmp_path: Path,
) -> None:
    # DC7, and the reason the configuration is read from the base ref at all: the tree under
    # review may not choose what is enforced over it. The anchor is `origin/main` in the
    # caller's own checkout, which the branch cannot write.
    project = _project_with_a_base(tmp_path, on_base=INSTALLED)
    (project / "keelline.toml").write_text(
        INSTALLED.replace('state = "installed"', 'state = "adopting"'), encoding="utf-8"
    )
    code, _written, printed = _run_base_step(project, tmp_path, INPUT_BASE="main")
    assert code == 1, printed
    assert "may not change an installed project's gate configuration" in printed, printed


@needs_git
@needs_bash
@needs_workflow
def test_the_base_ref_falls_back_to_the_pull_requests_base_and_then_the_default_branch(
    tmp_path: Path,
) -> None:
    # The three anchors, in the order the workflow reads them, and none of them is the tree
    # under review: the caller's `with:`, the pull request's base as the platform reports it,
    # and the repository's default branch. With none of the three the step refuses rather than
    # guessing a branch name.
    project = _project_with_a_base(tmp_path, on_base=INSTALLED)
    _code, written, _printed = _run_base_step(project, tmp_path, PR_BASE="main")
    assert written["base"] == "main"
    _code, written, _printed = _run_base_step(project, tmp_path, DEFAULT_BRANCH="main")
    assert written["base"] == "main"
    code, written, printed = _run_base_step(project, tmp_path)
    assert code == 1, printed
    assert "no base ref" in printed, printed
    assert written == {}, written


@needs_git
@needs_bash
@needs_workflow
def test_a_project_root_below_the_checkout_is_where_the_configuration_is_read_from(
    tmp_path: Path,
) -> None:
    # The `path:` input, which is what the smoke workflow and a monorepo use. It reaches the
    # shell through `env:` and is used as a path prefix, never as a command.
    project = _project_with_a_base(tmp_path, on_base=None)
    code, written, printed = _run_base_step(
        project, tmp_path, INPUT_BASE="main", INPUT_PATH="./sub/project/"
    )
    assert code == 0, printed
    assert written["root"] == "project/sub/project", written
    assert "sub/project/keelline.toml is not on origin/main" in printed, printed
