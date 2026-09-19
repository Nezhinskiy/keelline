"""The two fixture projects the smoke workflow runs against, held to what they claim.

`smoke-project` is a project every gate passes on, with `state = "installed"` so the gates
enforce; `hostile-project` (Task 15) is the S10 clone. Both are read by CI from this tree,
so a fixture that drifted from what a gate accepts would fail the smoke workflow with a
message about the fixture rather than about Keelline.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
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


# `${{ … }}` is YAML plain text and not flow syntax, so it is removed before a line is asked
# whether it carries a brace. Non-greedy, because two expressions on one line are two.
_EXPRESSION = re.compile(r"\$\{\{.*?\}\}")


def _scan(workflow: Path) -> Iterator[tuple[str, str]]:
    """The file, cut into what a `run:` key owns and everything else.

    **One rule, and it replaces four rounds of enumerating shapes: a `run:` key owns the rest of
    its own line and every following line indented past the KEY's column.** That is what YAML
    indentation means, and it is true of an inline one-liner, a block scalar, an indented plain
    scalar, a quoted scalar that wraps, and a plain scalar that continues onto the next line —
    without this function knowing which of those it is looking at. Enumerating them is what was
    wrong four times: a reader that knows five shapes is a reader that is blind to the sixth,
    and it reports clean while being so.

    The key's column and not the line's, because a step whose first key is `run` carries the
    list dash on the same line (the ordinary spelling for a step with no `name`), and measuring
    at the dash would make the step's own sibling keys part of its script — `env:` among them,
    which is exactly where a `${{ }}` belongs.

    **Everything a `run:` key introduces is collected, and nothing is classified.** Telling a
    script from something else needs a classifier, and a classifier fails by reading a script as
    settings — the same hole wearing the name of a feature. So the rule is applied to the key's
    NAME alone, and the cost of that is stated here rather than exempted away. It is a cry-wolf
    cost and never a hole: every case below fails loudly, in the safe direction, in front of
    whoever writes it.

    There are three of them, and they are one class and one consequence rather than a list to
    keep up with.

    **A key named `run` that is not a script.** `defaults: run:` is a mapping of `shell` and
    `working-directory`, and an action input that happens to be called `run` under `with:` is
    another. Both are collected and scanned identically. So
    `defaults: run: working-directory: ${{ inputs.path }}` — standard, correct Actions, and not
    an injection — fails the guard over these blocks. That is a decision for whoever first needs
    it to take deliberately, with a red test in front of them, rather than a hole dug in
    advance. Neither shape appears in this tree today.

    **A comment indented past a one-liner's key column**, which this rule introduced and the
    reader before it did not have: a one-liner used to be taken and the following lines left
    alone, and now the key owns them. So

        - run: echo a
            # never splice ${{ github.ref }} here — use env:

    is one body carrying an expression, and the guard fails pointing at a comment — which is
    exactly the comment a repository shipping this guard tends to write. Keeping it is the same
    trade as the first: the alternative is a rule that knows what a comment is, which is a
    classifier, which is the hole.

    What it yields: `("run", body)` for each `run:` key, and `("line", raw)` for every line
    outside one. The second stream exists so the brace refusal below can ask its question
    without a `run:` body's own braces answering it.
    """
    lines = workflow.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        index += 1
        if stripped.startswith("- "):
            stripped = stripped[2:].lstrip()
        if not stripped.startswith("run:"):
            yield "line", line
            continue
        indent = line.index("run:")
        body = [rest] if (rest := stripped[len("run:") :].strip()) else []
        while index < len(lines):
            following = lines[index]
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            body.append(following)
            index += 1
        yield "run", "\n".join(body)


def run_blocks(workflow: Path) -> list[str]:
    """Everything every `run:` key in the file owns, one string each."""
    return [body for kind, body in _scan(workflow) if kind == "run"]


def braced_lines(workflow: Path) -> list[str]:
    """Every line outside a `run:` body that still carries a brace once `${{ … }}` is removed.

    **What it is for** is the one shape the indentation rule above cannot reach: a step spelled
    as a flow mapping — `- {run: "…"}` — puts the whole step on one line inside braces, and
    there is no following line to own. It is **refused rather than parsed**: writing a
    flow-mapping parser is the enumeration again, one level down, and the failure mode of the
    thing that replaced is a shape nobody thought of. So the day a workflow spells a step that
    way, the guard says so loudly instead of silently not seeing it.

    **What it actually checks is broader than that, deliberately, and the name says so.** It
    reports anything brace-shaped rather than deciding what the braces mean — a flow sequence of
    mappings, a flow-style `matrix` entry, `extra: {a: 1}`, a quoted JSON-ish scalar such as
    `CFG: '{"a": 1}'`. All of those are refused too, and none of them is a flow-mapping step.
    Classifying them apart is the classifier again; refusing anything brace-shaped is the
    conservative answer, and the message a reader gets names the brace they wrote rather than a
    flow-mapping step that is not there. None of these shapes appears in this tree.

    `${{ … }}` is removed first because it is plain text that carries braces: without the strip
    every line of every workflow here would be reported, and a guard that cries wolf on every
    line is a guard somebody deletes. The strip is not a way past the check either — a brace
    outside an expression survives it, which is what `- {run: "echo ${{ x }}"}` is.

    Lines inside a `run:` body are not asked at all: a heredoc's own Python carries braces, and
    they are already scanned as the script they are.
    """
    return [
        line
        for kind, line in _scan(workflow)
        if kind == "line" and "{" in _EXPRESSION.sub("", line)
    ]


@needs_workflow
def test_no_workflow_splices_an_expression_into_a_shell() -> None:
    # The one class of workflow defect a text scan can catch, and the one worth catching: a
    # `${{ }}` inside a `run:` is interpolated by the platform before the shell sees the script,
    # so a ref name, a branch name or a pull-request title that carries shell metacharacters
    # runs as the workflow's own code. Every value in these files reaches a shell through
    # `env:` instead.
    #
    # `*.y*ml`: the platform reads `.yaml` too, and a workflow added with the other spelling
    # would never be scanned while the `>=` assertion below went on passing.
    workflows = sorted(WORKFLOWS.glob("*.y*ml"))
    assert {p.name for p in workflows} >= {"ci.yml", "check.yml", "smoke.yml"}, workflows
    read: list[str] = []
    for workflow in workflows:
        blocks = run_blocks(workflow)
        # Per file and not for all of them: `smoke-release.yml` is two reusable-workflow calls
        # and legitimately runs no shell at all, so the floor is on the three that do — a
        # reader that silently stopped finding blocks would otherwise pass on an empty walk.
        # Measured: check.yml 9, ci.yml 11, smoke.yml 6.
        if workflow.name in {"ci.yml", "check.yml", "smoke.yml"}:
            assert len(blocks) >= 5, (workflow.name, len(blocks))
        read.extend(blocks)
        for block in blocks:
            assert "${{" not in block, (workflow.name, block)
        # Refused and not classified: anything brace-shaped outside a `run:` body. What it is
        # for is the step spelled as a flow mapping — `- {run: "…"}` — which has no following
        # line for the indentation rule to own; what it reports is every brace, because deciding
        # which ones are a step is the classifier the rule above exists without.
        assert braced_lines(workflow) == [], (workflow.name, braced_lines(workflow))
    # Two floors and not one, for the reason the whole-tree gate needed two: a reader that
    # collects the right NUMBER of bodies and truncates each of them to its first line passes a
    # count and fails a size. Measured when written: 30 bodies, 7,761 characters.
    assert len(read) >= 25, len(read)
    assert sum(len(block) for block in read) >= 4000, sum(len(block) for block in read)


def test_a_run_key_owns_every_line_indented_past_it(tmp_path: Path) -> None:
    # The rule, stated as a case rather than as a list of shapes. Eight bodies in eight
    # spellings, each carrying an expression, so a body the reader truncates or cannot see is a
    # body the guard above reports clean. Five of these eight were holes in successive rounds;
    # the last two — a plain scalar that continues onto the next line and a quoted one that
    # wraps — are here because the rule covers them without being told to, which is the whole
    # of why it replaced the list. Mutations (declared): drop the continuation
    # loop, drop the value on the key's own line, drop the dash strip, measure the indent at
    # the line instead of the key.
    workflow = tmp_path / "synthetic.yml"
    workflow.write_text(
        "jobs:\n"
        "  one:\n"
        "    defaults:\n"
        "      run:\n"
        "        shell: bash ${{ inputs.shell }}\n"
        "    steps:\n"
        "      - run: >\n"
        "          echo folded ${{ github.ref }}\n"
        "      - run: |\n"
        "          echo dashed-block ${{ github.actor }}\n"
        "        env:\n"
        "          SAFE: ${{ github.sha }}\n"
        "      - run: echo inline ${{ github.job }}\n"
        "      - name: with a name of its own\n"
        "        run: echo named ${{ github.workflow }}\n"
        "      - name: an indented plain scalar, which carries no marker at all\n"
        "        run:\n"
        "          echo plain ${{ github.run_id }}\n"
        "      - run: echo continued\n"
        "          && echo ${{ github.event.pull_request.title }}\n"
        '      - run: "echo quoted\n'
        '          && echo ${{ github.head_ref }}"\n',
        encoding="utf-8",
    )
    blocks = run_blocks(workflow)
    # Eight: the seven scripts and the `defaults: run:` mapping. Every one of them was
    # collected by the same rule and every one of them is scanned, so the count below and the
    # scan above are over the same set — and no classifier has to tell a mapping from a script.
    assert len(blocks) == 8, blocks
    for wanted in ("folded", "dashed-block", "inline", "named", "plain", "continued", "quoted"):
        assert any(wanted in block for block in blocks), (wanted, blocks)
    # Every one of them carries its expression into the scan, which is the property the guard
    # rests on: a body collected but truncated at its first line reports clean. The two
    # continuation shapes are exactly that case — the value begins on the key's line and the
    # expression is on the next one.
    for block in blocks:
        assert "${{" in block, block
    continued = next(block for block in blocks if "continued" in block)
    assert "pull_request.title" in continued, continued
    quoted = next(block for block in blocks if "quoted" in block)
    assert "head_ref" in quoted, quoted
    # And the dashed block stops at its own `env:` rather than swallowing it — the direction
    # that would have produced a spurious finding on `env:`, which is where an expression
    # belongs.
    dashed = next(block for block in blocks if "dashed-block" in block)
    assert "SAFE" not in dashed, dashed
    assert braced_lines(workflow) == []


def test_a_step_spelled_as_a_flow_mapping_is_refused_rather_than_parsed(tmp_path: Path) -> None:
    # The one shape the indentation rule cannot reach, because there is no following line to
    # own. It is reported, not read: a flow-mapping parser would be the enumeration again one
    # level down, and the failure mode of the thing being replaced is a shape nobody thought
    # of. Mutation (declared): stop reporting it and the reader sees a workflow with one step
    # in it, silently.
    workflow = tmp_path / "flow.yml"
    workflow.write_text(
        "jobs:\n"
        "  one:\n"
        "    steps:\n"
        '      - {run: "echo flow ${{ github.actor }}"}\n'
        "      - run: echo ordinary\n",
        encoding="utf-8",
    )
    # The step in braces is not a `run:` body the reader can see...
    assert run_blocks(workflow) == ["echo ordinary"], run_blocks(workflow)
    # ...so it is named here instead, with the expression stripped before the question is asked
    # so that `${{ }}` — which is plain text, not flow syntax — cannot answer it.
    flow = braced_lines(workflow)
    assert len(flow) == 1, flow
    assert "run" in flow[0] and "{" in flow[0], flow


def test_an_expression_is_not_mistaken_for_flow_syntax(tmp_path: Path) -> None:
    # The negative of the test above, and the reason `_EXPRESSION` exists: every `${{ }}` in
    # these files carries braces, and a brace check that counted them would report every
    # workflow in the tree as a flow mapping — a guard that cries wolf on every line is a guard
    # somebody deletes.
    workflow = tmp_path / "ordinary.yml"
    workflow.write_text(
        "jobs:\n"
        "  one:\n"
        "    if: ${{ github.event_name == 'push' }}\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "        with:\n"
        "          ref: ${{ github.sha }} and ${{ github.ref }}\n",
        encoding="utf-8",
    )
    assert braced_lines(workflow) == []


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
