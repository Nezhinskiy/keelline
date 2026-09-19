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
HOSTILE = ROOT / "tests" / "fixtures" / "hostile-project"
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


def test_the_hostile_fixture_carries_the_three_properties_the_scenario_depends_on() -> None:
    # `scripts/smoke_exfiltration.py` asserts that each of these reaches nothing. A fixture
    # that had quietly lost one of them would make every row in that scenario green over a
    # clone that was never hostile, which is the shape this repository keeps finding.
    import json
    import tomllib

    raw = (HOSTILE / "keelline.toml").read_text(encoding="utf-8")
    config = tomllib.loads(raw)
    # The literal and not only the loaded value: `installed` is not the loader's default, and
    # a fixture that relied on a default would stop being the hostile case the day it moved.
    assert 'state = "installed"' in raw
    assert config["keelline"]["state"] == "installed"
    # The clone names ANOTHER project, which is the whole of the `mismatch` row.
    assert config["project"]["name"] == "smoke"
    assert config["memory"]["mode"] == "in-repo"

    note = (HOSTILE / "docs" / "memory" / "developer" / "canary.md").read_text(encoding="utf-8")
    assert "startup: -1" in note, note
    assert "CANARY-IN-REPO-RULE" in note

    settings = json.loads((HOSTILE / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "KEELLINE_CONFIG" in settings["env"]
    assert "PATH" in settings["env"]


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
        # `- run: …` as well as `run: …`: a step whose first key is `run` carries the list dash
        # on the same line, which is the ordinary spelling for a step with no `name`. No file in
        # this tree uses it today — the same reason the fold marker went unnoticed — and a
        # reader that cannot see it would report nothing for a whole workflow written that way.
        if stripped.startswith("- "):
            stripped = stripped[2:].lstrip()
        if not stripped.startswith("run:"):
            continue
        rest = stripped[len("run:") :].strip()
        # `defaults: run:` is a mapping of shell settings and not a script. It contributed an
        # empty string, which scanned clean and still counted toward the floor below — and that
        # floor is the only thing making the scan non-vacuous, so it may count only what it
        # scans.
        if not rest:
            continue
        # `>` and `>-` as well as `|`: a folded scalar is a script too, and sending one down the
        # one-liner path scanned the fold marker and let the whole body past. Nothing in the tree
        # uses `>` today, which is exactly why nobody would have noticed — and the body would
        # have gone on counting toward the floor while escaping the check.
        if not rest.startswith(("|", ">")):
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
    # `*.y*ml`: the platform reads `.yaml` too, and a workflow added with the other spelling
    # would never be scanned while the `>=` assertion below went on passing.
    workflows = sorted(WORKFLOWS.glob("*.y*ml"))
    assert {p.name for p in workflows} >= {"ci.yml", "check.yml", "smoke.yml"}, workflows
    read = 0
    for workflow in workflows:
        blocks = run_blocks(workflow)
        # Per file and not for all of them: `smoke-release.yml` is two reusable-workflow calls
        # and legitimately runs no shell at all, so the floor is on the three that do — a
        # reader that silently stopped finding blocks would otherwise pass on an empty walk.
        if workflow.name in {"ci.yml", "check.yml", "smoke.yml"}:
            assert len(blocks) >= 4, (workflow.name, len(blocks))
        read += len(blocks)
        for block in blocks:
            assert "${{" not in block, (workflow.name, block)
    assert read >= 20, read


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
def test_a_path_input_cannot_write_the_steps_own_outputs(tmp_path: Path) -> None:
    # `p` is appended to `$GITHUB_OUTPUT`, which the runner parses line by line, so a `path:`
    # carrying a newline used to write further `key=value` lines — and the keys the next steps
    # read are `base`, `state` and `enforce`, the last of which is the whole of the base-ref
    # rule's teeth. The caller already chooses `base:` by design, so this was not an escalation
    # of what it may decide; it was an unvalidated value on a control channel.
    project = _project_with_a_base(tmp_path, on_base=INSTALLED)
    code, written, printed = _run_base_step(
        project, tmp_path, INPUT_BASE="main", INPUT_PATH="sub\nenforce=true"
    )
    assert code == 1, printed
    assert "must be a plain relative path" in printed, printed
    assert written == {}, written
    # And the other half of the same check, so `root=` below is provably inside the checkout.
    code, written, printed = _run_base_step(
        project, tmp_path, INPUT_BASE="main", INPUT_PATH="../elsewhere"
    )
    assert code == 1, printed
    assert "must not leave the checkout" in printed, printed
    assert written == {}, written


@needs_git
@needs_bash
@needs_workflow
def test_the_base_branch_itself_is_exempt_from_the_equality_rule(tmp_path: Path) -> None:
    # DC7's strict form applies "on any branch but the base branch itself". A push to the base
    # branch IS the change, so comparing it against `origin/<base>` would refuse every merge —
    # and the arm that exempts it had no test.
    project = _project_with_a_base(tmp_path, on_base=INSTALLED)
    (project / "keelline.toml").write_text(
        INSTALLED.replace('state = "installed"', 'state = "installed"\nprofile = ""'),
        encoding="utf-8",
    )
    code, written, printed = _run_base_step(
        project, tmp_path, INPUT_BASE="main", CURRENT_REF="refs/heads/main"
    )
    assert code == 0, printed
    assert written["state"] == "installed", written
    assert written["enforce"] == "true", written
    assert "::error" not in printed, printed


@needs_git
@needs_bash
@needs_workflow
def test_a_differing_configuration_under_a_base_that_is_not_installed_warns(
    tmp_path: Path,
) -> None:
    # The advisory half of the same comparison (D8): while the base's state is `adopting` the
    # branch may change the configuration, and the run says so rather than refusing. Without
    # this the refusal arm and the warning arm are one untested branch between them.
    adopting = INSTALLED.replace('state = "installed"', 'state = "adopting"')
    project = _project_with_a_base(tmp_path, on_base=adopting)
    (project / "keelline.toml").write_text(INSTALLED, encoding="utf-8")
    code, written, printed = _run_base_step(project, tmp_path, INPUT_BASE="main")
    assert code == 0, printed
    assert written["state"] == "adopting", written
    assert written["enforce"] == "false", written
    assert "::warning" in printed and "advisory while the base's state is adopting" in printed
    assert "::error" not in printed, printed


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


def test_the_reader_sees_a_folded_script_and_not_a_shell_settings_mapping(tmp_path: Path) -> None:
    # The two ways the scan above could have read a file and still checked nothing, on a
    # synthetic workflow rather than on the tree — the tree is exactly where neither shape
    # appears, which is why neither was noticed. Mutation (declared): narrow the reader back to
    # `rest.startswith("|")` and the folded body walks through with an expression in it.
    workflow = tmp_path / "synthetic.yml"
    workflow.write_text(
        "jobs:\n"
        "  one:\n"
        "    defaults:\n"
        "      run:\n"
        "        shell: bash\n"
        "    steps:\n"
        "      - run: >\n"
        "          echo folded ${{ github.ref }}\n"
        "      - run: |\n"
        "          echo literal\n"
        "      - run: echo inline\n"
        "      - name: with a name of its own\n"
        "        run: echo named\n",
        encoding="utf-8",
    )
    blocks = run_blocks(workflow)
    # Four scripts, and the `defaults: run:` mapping is not one of them — it scanned clean and
    # counted toward the floor that exists to make the scan non-vacuous.
    assert len(blocks) == 4, blocks
    assert any("folded" in block and "${{" in block for block in blocks), blocks
    assert any(block.strip() == "echo literal" for block in blocks), blocks
    assert "echo inline" in blocks, blocks
    assert "echo named" in blocks, blocks


# --- `check.yml`'s verdict step, run as the shell script it is --------------------------

VERDICT_STEP = "Verdict"


def _run_verdict(tmp_path: Path, **environment: str) -> tuple[int, str]:
    done = subprocess.run(
        ["bash", "-e", "-c", step_script(CHECK_WORKFLOW, VERDICT_STEP)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "ENFORCE": "false",
            "STATE": "absent",
            "O_DOCS": "success",
            "O_BUGS": "success",
            "O_PLAN": "success",
            "O_COMMIT": "success",
            "O_TRAIL": "success",
            **environment,
        },
    )
    return done.returncode, done.stdout + done.stderr


@needs_bash
@needs_workflow
def test_the_verdict_fails_the_job_only_where_the_base_says_installed(tmp_path: Path) -> None:
    # D8 in three lines of shell, and the reviewer's point that reading it is not running it.
    # Enforcing and clean is the control: a verdict that failed there would be noticed at once,
    # and one that passes everything would not.
    code, printed = _run_verdict(tmp_path, ENFORCE="true", STATE="installed")
    assert code == 0, printed
    assert "::error" not in printed and "::warning" not in printed, printed

    code, printed = _run_verdict(tmp_path, ENFORCE="true", STATE="installed", O_DOCS="failure")
    assert code == 1, printed
    assert "::error::docs failed" in printed, printed

    code, printed = _run_verdict(tmp_path, ENFORCE="false", STATE="adopting", O_DOCS="failure")
    assert code == 0, printed
    assert "::warning::docs failed, advisory while the base's state is adopting" in printed
    assert "::error" not in printed, printed


@needs_bash
@needs_workflow
def test_every_gate_is_named_in_the_verdict_and_not_only_the_first(tmp_path: Path) -> None:
    # "Every gate ran, whatever the first one said" is the step's own claim, and a loop that
    # stopped at the first failure would satisfy every assertion above.
    code, printed = _run_verdict(
        tmp_path,
        ENFORCE="true",
        STATE="installed",
        O_DOCS="failure",
        O_BUGS="failure",
        O_PLAN="failure",
        O_COMMIT="failure",
        O_TRAIL="failure",
    )
    assert code == 1, printed
    for name in ("docs", "bugs", "plan", "commit", "trail"):
        assert f"::error::{name} failed" in printed, (name, printed)
