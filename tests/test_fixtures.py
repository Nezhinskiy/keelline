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
from collections.abc import Iterator
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run
from tests.gitfixture import git
from tests.workflow_yaml import load

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "tests" / "fixtures" / "smoke-project"
HOSTILE = ROOT / "tests" / "fixtures" / "hostile-project"
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
PLAN = "docs/plans/2026-09-19-the-fixtures-own-plan.md"


def _copy_as_repository(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(SMOKE, root)

    # Two commits, so that `commit check --range HEAD~1..HEAD` checks one message rather than
    # an empty range that proves nothing. The second one touches the fixture's own plan rather
    # than being empty, for the same reason one step further on: `plan check --base HEAD~1`
    # lints the plans that range touches, and a range that touches none exits 0 having linted
    # nothing. `test_plan_check_on_the_fixture_lints_the_plan_it_touched` is what says so.
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: the fixture")
    plan = root / PLAN
    added = plan.read_text(encoding="utf-8") + "\nA line the second commit adds.\n"
    plan.write_text(added, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "docs: a second one")
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
@pytest.mark.parametrize(
    ("argv", "examined"),
    [
        (["bugs", "check"], {"checked": True, "findings": []}),
        (["commit", "check", "--range", "HEAD~1..HEAD"], {"commits": 1, "violations": []}),
        (["docs", "trail", "--check"], {"stale": False}),
    ],
    ids=("bugs check", "commit check", "docs trail --check"),
)
def test_the_gates_on_the_fixture_report_what_they_examined(
    tmp_path: Path, argv: list[str], examined: dict[str, object]
) -> None:
    # The non-vacuity companions for three more of the five rows above, written for the reason
    # the `plan check` one was: `exit 0` is also what a gate that examined nothing produces,
    # and the author closed that for one row and not for the rest. Measured on this tree, each
    # guard torn out on its own and `tests/test_fixtures.py` run:
    #   `ledger/check.py`'s `uninitialised()` -> `return True`, so `bugs check` takes its inert
    #     arm and reports `{"checked": False}` having read no ledger — 30 passed;
    #   `guards/commit.py`'s `commits = commits_in(root, rev_range)` -> `commits = []`, so the
    #     range is empty and the gate says "OK: 0 commit message(s) checked" — 30 passed.
    # The quantity each row is about is what is asserted here, so those two now redden.
    # `docs trail --check` carries `stale` for the same reason; its own guard is held by the
    # hand-measured fixture mutation named above.
    #
    # Mutations (declared): the bug ledger reports itself uninitialised; the commit gate reads
    # an empty range.
    import json

    root = _copy_as_repository(tmp_path)
    code, printed = _invoke(root, tmp_path, [*argv, "--json"])
    assert code == 0, printed
    data = json.loads(printed)
    for key, value in examined.items():
        assert data[key] == value, (key, data)


@needs_git
def test_docs_check_on_the_fixture_reads_the_documents_it_is_about(tmp_path: Path) -> None:
    # The fifth row's companion, and it has to be a planted violation rather than a count:
    # `docs check` reports `findings: []` and the same `OK:` line whether it examined the
    # documents or returned early, so no field of its success answer can tell the two apart.
    # Measured: `check_budgets` and `check_links` in `src/keelline/docs/hygiene.py` each given
    # `return []` as their first statement left `tests/test_fixtures.py` 30 green.
    #
    # Two plants and not one, because they are two walks: an always-loaded document blown past
    # its line budget, and a link out of it to a file that is not there.
    #
    # Mutations (declared): the budget walk returns nothing; the link walk returns nothing.
    import json

    root = _copy_as_repository(tmp_path)
    agents = root / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8")
        + "\n[a link to nothing](docs/not-a-file.md)\n"
        + "\nfiller\n" * 2000,
        encoding="utf-8",
    )
    code, printed = _invoke(root, tmp_path, ["docs", "check", "--json"])
    assert code == 1, printed
    rules = {finding["rule"] for finding in json.loads(printed)["findings"]}
    assert "agents-lines" in rules, rules
    assert "missing-link" in rules, rules


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
# which base commit the gates' configuration comes from and which project root the gates run
# in. That step's `run:` body is extracted from the shipped file — never retyped here, or the
# test would hold a copy and the file would be free to drift — and run with `bash` against real
# repositories.

CHECK_WORKFLOW = ROOT / ".github" / "workflows" / "check.yml"
BASE_STEP = "The base ref and the project root"
needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")
# `.github/` is outside `source-include`: it is this repository's own continuous integration
# and not source a downstream packager needs, and `scripts/check_artifacts.py` states that the
# sdist exists so such a packager can run the suite. So the cases below skip where the file
# they are about is not there, rather than the tree gaining a line to ship CI configuration.
# Five cases here really do run `check.yml`'s base step, and `tests/test_check_workflow.py`
# imports this marker for its own, which run the two gate steps.
needs_workflow = pytest.mark.skipif(
    not CHECK_WORKFLOW.is_file(), reason="check.yml is not in the sdist"
)
# And its own marker for the one guard that is not about `check.yml` at all. The tree-wide
# `${{ }}`-in-`run:` scan is the only assertion covering `ci.yml`, `release.yml` and
# `smoke.yml`, and it carried `needs_workflow` — so renaming or deleting `check.yml` would
# have switched off the guard over the other four, silently and green. A guard whose predicate
# is unrelated to what it guards is a guard that will eventually be off without anyone
# deciding it should be.
needs_workflows_dir = pytest.mark.skipif(
    not (ROOT / ".github" / "workflows").is_dir(), reason="the workflows are not in the sdist"
)


CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
needs_ci_workflow = pytest.mark.skipif(
    not CI_WORKFLOW.is_file(), reason="ci.yml is not in the sdist"
)
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
PR_TEMPLATE = ROOT / ".github" / "pull_request_template.md"
_SHORT_VERSION = re.compile(
    r"^## The short version\n.*?^```bash\n(.*?)^```", re.MULTILINE | re.DOTALL
)
_TEMPLATE_BLOCK = re.compile(r"^## Verification\n.*?^```\n(.*?)^```", re.MULTILINE | re.DOTALL)
_COVERAGE_FLOOR = re.compile(r"--cov-fail-under=(\d+)")


@needs_ci_workflow
def test_the_block_a_contributor_copies_is_the_one_ci_runs() -> None:
    """The two blocks a contributor runs before pushing, against what CI actually runs.

    They listed five commands and CI ran seven: no coverage floor on the `pytest` line while
    `ci.yml` fails below 92%, and no mutation oracle at all — the project's headline
    obligation, missing from the one block a contributor copies. A contributor who followed
    `CONTRIBUTING.md` exactly got a green tree and a red pull request, twice over.

    Bound rather than restated: the floor is read out of `ci.yml`'s own `pytest` invocation, so
    raising it in CI reddens here until both documents move with it.
    """
    # Mutation: drop the mutation-oracle line from `CONTRIBUTING.md`'s block -> reddens naming
    # it. The floor first: a `run:` walk that returned nothing would satisfy every `in` below
    # by making `ci` the empty string.
    bodies = run_blocks(CI_WORKFLOW)
    assert len(bodies) == EXPECTED_BLOCKS["ci.yml"], len(bodies)
    ci = "\n".join(bodies)
    floor = _COVERAGE_FLOOR.search(ci)
    assert floor is not None, "ci.yml no longer runs pytest with a coverage floor"

    blocks = {}
    match = _SHORT_VERSION.search(CONTRIBUTING.read_text(encoding="utf-8"))
    assert match is not None, "CONTRIBUTING.md has no `## The short version` bash block"
    blocks["CONTRIBUTING.md"] = match.group(1)
    match = _TEMPLATE_BLOCK.search(PR_TEMPLATE.read_text(encoding="utf-8"))
    assert match is not None, "the pull-request template has no `## Verification` block"
    blocks[".github/pull_request_template.md"] = match.group(1)

    # Every gate the contributor is asked to run locally, in the spelling CI runs it in.
    required = (
        f"--cov-fail-under={floor.group(1)}",
        "scripts/mutation_oracle.py",
        "ruff check .",
        "ruff format --check .",
        "mypy",
        "keelline release check",
    )
    for name, text in blocks.items():
        assert text.strip(), name
        missing = [gate for gate in required if gate not in text]
        assert missing == [], (name, missing)
        # And each one is really a gate CI runs, so the block cannot drift into naming a
        # command nobody checks.
        assert all(gate in ci for gate in required), [g for g in required if g not in ci]


ORACLE_COMMAND = "scripts/mutation_oracle.py"
ORACLE_JOB = "oracle"
# Measured on the `oracle` job's own run: 173 s for the 566 entries `mutations.toml` held that
# day, four jobs on `ubuntu-latest` against a warm bytecode cache. It was 751 s for 372 while the
# oracle ran one entry at a time and compiled from source on every run. Re-measure it from that
# job's runs; it is here as a number rather than as prose so that the budget below is checked
# rather than described.
ORACLE_SECONDS_PER_ENTRY = 173 / 566
# Checkout, `setup-uv` against a warm cache and `uv sync --locked` — the whole of the job that
# is not the oracle itself. Estimated from the 128 s of non-oracle work in `checks` on the same
# runner, which also carries lint, types, the test run, the build and a wheel install.
ORACLE_SETUP_SECONDS = 60
# The runner-variance allowance the job's own comment in `ci.yml` reserves: a nominally 889 s job
# was cancelled at 918 s, about 30 s of slip, and this doubles it. Projected without it, this test
# stayed green some thirty entries past the point that comment says to raise the budget.
ORACLE_VARIANCE_SECONDS = 60


def _ci_jobs() -> dict[str, list[str]]:
    """Every job in `ci.yml`, as the raw lines underneath it.

    Indentation arithmetic and not a YAML parser, for the reason `_release_jobs` gives further
    down and `_scan` gives at length: this repository ships no runtime dependency and
    `tests/test_import_boundary.py` is why none arrives through a test either. A job is a key at
    indent 2 under `jobs:` that ends in a colon; everything until the next one belongs to it.
    """
    jobs: dict[str, list[str]] = {}
    current: str | None = None
    inside = False
    for line in CI_WORKFLOW.read_text(encoding="utf-8").splitlines():
        if line.rstrip() == "jobs:":
            inside = True
            continue
        if not inside:
            continue
        bare = line.lstrip()
        opens_job = len(line) - len(bare) == 2 and line.rstrip().endswith(":")
        if bare and not bare.startswith("#") and opens_job:
            current = line.strip().rstrip(":")
            jobs[current] = []
            continue
        if current is not None:
            jobs[current].append(line)
    return jobs


@needs_ci_workflow
def test_the_mutation_oracle_has_a_job_of_its_own_with_a_budget_that_fits() -> None:
    """The oracle runs once, in a job nothing can skip, under a bound that fits the set.

    It used to be a step of `checks`, where it was 76% of the job: 751 s of 879 s on Linux
    against a 900 s bound, on all four configurations at once, and the branch that took
    `mutations.toml` past 380 entries took `checks (macos-latest, 3.13)` over the bound. Running
    it on one configuration was necessary and not sufficient — `timeout-minutes` is a per-job
    bound, so paying once instead of four times gave 751 s back to the three configurations that
    stopped running it and nothing to the one that still did.

    **Three things are asserted, and each is a way this has already gone wrong or could go
    quiet.** That exactly one job runs the oracle, because a second copy would pay twice again
    and a zeroth would be the set silently switched off. That the job carries no `if:` and no
    `strategy:`, because a skipped job reports as green — the "reads as coverage" failure in the
    costume of a condition — and because a matrix would reintroduce the multiplication. And that
    the budget still fits the set it has to prove.

    **The budget assertion is the one that earns its place.** The oracle grows by construction:
    the rule is that every new assertion ships with the mutation that reddens it, so the entry
    count only goes up, at about a third of a second each on four CPUs. Projecting the cost from
    the live entry count means the next branch to outgrow the bound reddens *here*, in a
    contributor's own test run, rather than as a cancelled job minutes into CI. That is the whole
    difference between arithmetic somebody can act on and arithmetic somebody discovers.

    No mutation travels with `ORACLE_SECONDS_PER_ENTRY` itself: lowering it weakens the
    projection without reddening anything, so there is nothing for an entry to catch. It is a
    measurement, and the comment beside it says to re-measure it from this job's own runs.
    """
    # Mutations (declared): the budget cut below the projection; the job given an `if:` that can
    # skip it. Both redden this case.
    import tomllib

    jobs = _ci_jobs()
    # The walk first: an empty reading would make every "exactly one" below come out zero for a
    # reason that is not about the workflow.
    assert len(jobs) >= 2, jobs
    holding = [name for name, body in jobs.items() if any(ORACLE_COMMAND in x for x in body)]
    assert holding == [ORACLE_JOB], holding

    body = jobs[ORACLE_JOB]
    skippable = [x for x in body if x.strip().startswith("if:")]
    assert skippable == [], (
        f"the {ORACLE_JOB!r} job can be skipped, and a skipped job reports as a green check",
        skippable,
    )
    multiplied = [x for x in body if x.strip().startswith(("strategy:", "matrix:"))]
    assert multiplied == [], (
        f"the {ORACLE_JOB!r} job runs a matrix, which is the four-fold cost this shape removed",
        multiplied,
    )

    bounds = [x for x in body if x.strip().startswith("timeout-minutes:")]
    assert len(bounds) == 1, bounds
    budget = int(bounds[0].split(":", 1)[1].strip()) * 60
    entries = len(tomllib.loads((ROOT / "mutations.toml").read_text(encoding="utf-8"))["mutation"])
    assert entries > 0, "mutations.toml declares nothing, so this projects no cost at all"
    projected = entries * ORACLE_SECONDS_PER_ENTRY + ORACLE_SETUP_SECONDS + ORACLE_VARIANCE_SECONDS
    assert budget >= projected, (
        f"{entries} mutation entries project ~{projected:.0f} s against a {budget} s bound — "
        f"raise `timeout-minutes` on the {ORACLE_JOB!r} job, and say in the comment what the "
        "new number buys in entries",
        budget,
        projected,
    )


WORKFLOWS = ROOT / ".github" / "workflows"
# The workflows that run a shell, so a per-file floor is a claim about them and an empty walk
# cannot pass. `smoke-release.yml` is out because it is two reusable-workflow calls and
# legitimately runs none — measured, 0 blocks — and that is the only file with an exemption.
SCRIPTED = {"ci.yml", "check.yml", "release.yml", "smoke.yml"}
# What `run_blocks` returns for each shipped workflow, measured 2026-09-19 with this module's
# own reader. Equalities rather than floors: the `>= 5` per file and `>= 25` overall they
# replace left seven of thirty-three bodies droppable, five of them `ci.yml`'s, with this
# module green — and the character floor at 4,000 against a measured 8,097 did not close the
# truncation shape its own comment claimed it closed (every body cut to eight lines came to
# 4,059). `smoke-release.yml` is two reusable-workflow calls and legitimately runs no shell,
# which is why it is 0 here rather than exempt from the walk.
EXPECTED_BLOCKS = {
    # 10 -> 6 when the base step stopped reading the state and the five gate steps and the shell
    # verdict became two `keelline gate` steps: the `defaults: run:` mapping, the checkout
    # assertion, the proof that Keelline runs, the base step, the judging step and the custom
    # gates' step.
    "check.yml": 6,
    # 12 -> 13 when the mutation oracle became a job of its own: the step left `checks` and the
    # new job carries its own `uv sync --locked` beside it, so one body moved and one was added.
    "ci.yml": 13,
    "release.yml": 7,
    "smoke-release.yml": 0,
    "smoke.yml": 6,
}
# And the size, per file, so a reader that returns the right NUMBER of bodies and truncates
# each of them reddens on the file it truncated rather than against a whole-set total with
# headroom in it. Floors and not equalities, because a workflow gaining a line is ordinary and
# a workflow losing half its script is not.
EXPECTED_CHARACTERS = {
    # Re-measured when the import proof and the pull-request base refusal landed: 5030 -> 6503.
    # Kept level with the measurement rather than left where it was, because a floor with a
    # thousand characters of headroom under it is a floor a truncation walks past. 6503 -> 6888
    # when the base step's reader stopped importing from the tree under review. 6888 -> 4776
    # when the base step stopped reading the state and the five gate steps and the shell verdict
    # became two `keelline gate` steps: the logic they held moved into the command. 4776 -> 4773
    # when a comment stopped calling the custom step a judging step.
    "check.yml": 4773,
    # 882 -> 899 for the same move: `uv sync --locked` is the body the oracle's own job added.
    "ci.yml": 899,
    "release.yml": 1683,
    "smoke-release.yml": 0,
    "smoke.yml": 3042,
}


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
    advance.

    **The first of those two shapes is already in this tree**, and saying otherwise was how
    the cost stopped being visible: `check.yml`'s `defaults: run:` mapping is this reader's
    first collected block for that file, scanned as a body like any other. It is harmless
    because it carries only `shell: bash` and no expression — and it is exactly where
    `working-directory: ${{ inputs.path }}` would be written, so the next person to reach for
    that hits the red test this paragraph exists to explain rather than one it told them
    could not happen.

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


@needs_workflows_dir
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
    assert {p.name for p in workflows} >= SCRIPTED, workflows
    # Equality, so a workflow added to this directory fails here — naming it — rather than
    # raising `KeyError` inside the loop, which is a redness about a missing dictionary key and
    # not about an unmeasured file.
    assert {p.name for p in workflows} == set(EXPECTED_BLOCKS), workflows
    read: list[str] = []
    for workflow in workflows:
        blocks = run_blocks(workflow)
        # Per file and not for all of them, and the measured count as an EQUALITY. The `>= 5`
        # per file and `>= 25` overall that stood here left seven of the bodies droppable and
        # the character floor at 4,000 left every body truncatable to eight lines. Measured on
        # this tree, against this test alone: `run_blocks` returning the first seven bodies of
        # each file — GREEN; every body cut to its first eight lines — GREEN. With the
        # equalities: `('check.yml', 7) … 7 == 9` and `('check.yml', 1264) … 1264 >= 5030`.
        # An equality moves when somebody edits a workflow, which is exactly when a reader
        # regression would otherwise hide behind the headroom.
        #
        # `smoke-release.yml` is in the table at 0 rather than exempt from the walk: it is two
        # reusable-workflow calls and legitimately runs no shell, and an exemption nobody can
        # see is how a file stops being read without anybody deciding that.
        #
        # No `mutations.toml` entry travels with the table itself, and the reason is that there
        # is nothing for one to mutate: a number changed here reddens this assertion by
        # construction, which proves the arithmetic rather than the reader. What has to be
        # load-bearing is the reader, and that is held by the four `_scan` entries already in
        # `mutations.toml`, one of which reddens this very case.
        assert len(blocks) == EXPECTED_BLOCKS[workflow.name], (workflow.name, len(blocks))
        size = sum(len(block) for block in blocks)
        assert size >= EXPECTED_CHARACTERS[workflow.name], (workflow.name, size)
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
    # count and fails a size. The per-file assertions above are what do the work now; these are
    # the whole-set restatement, at the measured values rather than at half of them.
    # Re-measured when `check.yml` became one job running `keelline gate`: 32 bodies, 10,397
    # characters (check.yml 4,773, ci.yml 899, release.yml 1,683, smoke.yml 3,042,
    # smoke-release.yml 0). The 12,127 before it counted the shell verdict and the state
    # reader that moved into the command; the floor is the sum of the per-file figures above, so
    # the two restate each other rather than one carrying slack the other does not.
    assert len(read) == sum(EXPECTED_BLOCKS.values()), len(read)
    assert sum(len(block) for block in read) >= 10_397, sum(len(block) for block in read)


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
    """The named step's script, straight out of the shipped file.

    Read by `tests.workflow_yaml`'s strict reader, which reads the whole file or fails: the
    line reader this replaced looked for `run: |` from the step's name to the end of the file,
    so a step whose script was spelled another way handed back the next step's, and a case
    about one step ran another. Exactly one step of that name, in any job, and it has a script.
    """
    document = load(workflow.read_text(encoding="utf-8"))
    assert isinstance(document, dict), document
    jobs = document.get("jobs")
    assert isinstance(jobs, dict), jobs
    found = [
        step
        for job in jobs.values()
        if isinstance(job, dict) and isinstance(job.get("steps"), list)
        for step in job["steps"]  # type: ignore[union-attr]
        if isinstance(step, dict) and step.get("name") == step_name
    ]
    assert len(found) == 1, (step_name, found)
    script = found[0].get("run")
    assert isinstance(script, str), (step_name, found[0])
    # No `${{ }}` may survive into the script: every value the step uses arrives through
    # `env:`, and one spliced into `run:` would be a command injection the test would run.
    assert "${{" not in script, script
    return script if script.endswith("\n") else script + "\n"


def test_a_step_s_script_is_never_read_from_the_step_after_it(tmp_path: Path) -> None:
    # The cases that run `check.yml`'s steps name a step and get its script. A reader that
    # searched onward for `run: |` handed back the next step's script for a step spelled with a
    # one-line `run:`, so a case about the first step ran the second. The strict reader gives
    # each step its own.
    workflow = tmp_path / "two.yml"
    workflow.write_text(
        "jobs:\n"
        "  one:\n"
        "    steps:\n"
        "      - name: first\n"
        "        run: echo first\n"
        "      - name: second\n"
        "        run: |\n"
        "          echo second\n",
        encoding="utf-8",
    )
    assert step_script(workflow, "first") == "echo first\n"
    assert step_script(workflow, "second") == "echo second\n"


def _project_with_a_base(tmp_path: Path, *, on_base: str | None) -> Path:
    """A clone whose `origin/main` carries `on_base` as `keelline.toml`, or carries none.

    The upstream also has a branch `a-branch-the-author-pushed`, so the clone tracks it: the
    disagreement case then meets a `base:` naming a branch that exists, which is the attack,
    and not a missing ref that fails for another reason. Measured when the case was written:
    with the branch absent the step with its refusal removed still exits 1, "not in this
    checkout"; with it present it exits 0.
    """
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    git(upstream, "init", "-q", "-b", "main")
    (upstream / "README.md").write_text("# a project\n", encoding="utf-8")
    if on_base is not None:
        (upstream / "keelline.toml").write_text(on_base, encoding="utf-8")
    git(upstream, "add", "-A")
    git(upstream, "commit", "-qm", "chore: base")
    git(upstream, "branch", "a-branch-the-author-pushed")
    project = tmp_path / "project"
    git(tmp_path, "clone", "-q", str(upstream), str(project))
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
            # The step runs no interpreter: git and the shell's own builtins are all it needs.
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "GITHUB_OUTPUT": str(output),
            "INPUT_BASE": "",
            "INPUT_PATH": ".",
            "PR_BASE": "",
            "DEFAULT_BRANCH": "",
            **environment,
        },
    )
    emitted = output.read_text(encoding="utf-8").splitlines()
    written = dict(line.split("=", 1) for line in emitted if "=" in line)
    return done.returncode, written, done.stdout + done.stderr


INSTALLED = '[keelline]\nversion = "0.1.0"\nstate = "installed"\n\n[project]\nname = "p"\n'


def _main(project: Path) -> str:
    """The commit the clone's remote-tracking `main` names: the base every case expects."""
    return git(project, "rev-parse", "refs/remotes/origin/main").strip()


@needs_git
@needs_bash
@needs_workflow
def test_a_tag_named_like_the_tracking_branch_does_not_choose_the_base(tmp_path: Path) -> None:
    """git resolves a short `origin/main` through `refs/tags/` before `refs/remotes/`, and
    `fetch-depth: 0` fetches every tag, so whoever may push a tag of that name would choose the
    configuration every pull request is judged against. The step resolves the fully qualified
    tracking ref, once, and every later read uses the commit it wrote.

    Mutation (declared): the short `origin/$base^{commit}` in place of the qualified name ->
    `base_sha` is the tag's commit.
    """
    project = _project_with_a_base(tmp_path, on_base=INSTALLED)
    (project / "keelline.toml").write_text(
        INSTALLED.replace('state = "installed"', 'state = "initialised"'), encoding="utf-8"
    )
    git(project, "add", "-A")
    git(project, "commit", "-qm", "chore: loosen")
    git(project, "tag", "origin/main")
    git(project, "checkout", "-q", "--detach", "HEAD~1")
    code, written, printed = _run_base_step(project, tmp_path, PR_BASE="main")
    assert code == 0, printed
    assert written["base_sha"] == _main(project), (written, printed)
    assert written["base_sha"] != git(project, "rev-parse", "refs/tags/origin/main").strip()


@needs_git
@needs_bash
@needs_workflow
def test_a_base_input_that_disagrees_with_the_pull_requests_own_base_is_refused(
    tmp_path: Path,
) -> None:
    """The caller's `base:` may not choose the configuration a pull request is judged against.

    On a `pull_request` event the platform runs the workflow file from the merge commit — the
    author's copy — and `with: base:` lives in it. So a pull request could point `base:` at a
    branch it had pushed, whose `keelline.toml` enforces nothing, and be judged against that
    without touching the tree's own `keelline.toml`.

    The platform's `github.base_ref` is the answer that cannot be written from the branch, so
    where both are present and they disagree the step refuses, and never echoes the author's
    value, which has not been validated and could carry a workflow command of its own. This
    costs a legitimate caller nothing: on a pull request `base:` decides nothing anyway, which
    the agreeing case below is here to keep true.

    Mutation (declared): the disagreement test is removed -> this reddens on the exit code.
    """
    project = _project_with_a_base(tmp_path, on_base=INSTALLED)
    code, written, printed = _run_base_step(
        project, tmp_path, INPUT_BASE="a-branch-the-author-pushed", PR_BASE="main"
    )
    assert code == 1, printed
    assert "this pull request's base is 'main'" in printed, printed
    assert "a-branch-the-author-pushed" not in printed, printed
    # Nothing was written, so no later step can read a base commit from this run.
    assert written == {}, written

    # Agreeing is not refused, and `base:` still decides on every event that reports no base —
    # which is what makes the refusal free.
    code, written, printed = _run_base_step(project, tmp_path, INPUT_BASE="main", PR_BASE="main")
    assert code == 0, printed
    assert written["base_sha"] == _main(project), written


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
    assert written["base_sha"] == _main(project), written
    _code, written, _printed = _run_base_step(project, tmp_path, DEFAULT_BRANCH="main")
    assert written["base_sha"] == _main(project), written
    code, written, printed = _run_base_step(project, tmp_path)
    assert code == 1, printed
    assert "no base ref" in printed, printed
    assert written == {}, written


@needs_git
@needs_bash
@needs_workflow
def test_a_path_input_cannot_write_the_steps_own_outputs(tmp_path: Path) -> None:
    # `p` is appended to `$GITHUB_OUTPUT`, which the runner parses line by line, so a `path:`
    # carrying a newline would write further `key=value` lines — and `base_sha` is the commit
    # whose configuration governs the gates. A forged one would choose it.
    project = _project_with_a_base(tmp_path, on_base=INSTALLED)
    code, written, printed = _run_base_step(
        project, tmp_path, INPUT_BASE="main", INPUT_PATH=f"sub\nbase_sha={'0' * 40}"
    )
    assert code == 1, printed
    assert "must be a plain relative path" in printed, printed
    assert written == {}, written
    # And the other half of the same check, so `root=` below stays inside the checkout.
    code, written, printed = _run_base_step(
        project, tmp_path, INPUT_BASE="main", INPUT_PATH="../elsewhere"
    )
    assert code == 1, printed
    assert "must not leave the checkout" in printed, printed
    assert written == {}, written


@needs_git
@needs_bash
@needs_workflow
def test_a_project_root_below_the_checkout_is_where_the_gates_run(tmp_path: Path) -> None:
    # The `path:` input, which is what the smoke workflow and a monorepo use. It reaches the
    # shell through `env:` and is used as a path prefix, never as a command.
    project = _project_with_a_base(tmp_path, on_base=None)
    code, written, printed = _run_base_step(
        project, tmp_path, INPUT_BASE="main", INPUT_PATH="./sub/project/"
    )
    assert code == 0, printed
    assert written["root"] == "project/sub/project", written


RELEASE_WORKFLOW = WORKFLOWS / "release.yml"
GATE_JOB = "environment-gate"
GATE_STEP = "The pypi environment is a gate and not a name GitHub invented"
needs_release_workflow = pytest.mark.skipif(
    not RELEASE_WORKFLOW.is_file(), reason="release.yml is not in the sdist"
)


def _release_jobs() -> dict[str, dict[str, str]]:
    """Every job in `release.yml`, with the two keys this module asks about.

    Indentation arithmetic rather than a YAML parser: the package carries no runtime
    dependency and `tests/test_import_boundary.py` is why none arrives through a test either,
    and `environment:` and `needs:` are each written on one line in this file. A job that stops
    writing them that way is a finding for whoever writes it, so the callers below assert the
    walk found something rather than trusting it to have.
    """
    jobs: dict[str, dict[str, str]] = {}
    current: str | None = None
    inside = False
    for line in RELEASE_WORKFLOW.read_text(encoding="utf-8").splitlines():
        if line.rstrip() == "jobs:":
            inside = True
            continue
        if not inside or not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 2 and line.rstrip().endswith(":"):
            current = line.strip().rstrip(":")
            jobs[current] = {}
        elif indent == 4 and current is not None and ":" in line:
            key, _, value = line.strip().partition(":")
            if key in ("environment", "needs"):
                jobs[current][key] = value.split("#")[0].strip()
    return jobs


def _gate_environment() -> str:
    """The environment name the gate step reads, out of its own `env:` block."""
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^\s+ENVIRONMENT: (\S+)$", text, re.M)
    assert match is not None
    return match.group(1)


@needs_release_workflow
def test_every_job_behind_the_pypi_environment_waits_for_the_environment_gate() -> None:
    """The property, stated over the file rather than over two hand-kept copies of a step.

    GitHub auto-creates an environment a job names and the repository lacks, with no protection
    rules on it, so `environment: pypi` is a gate only if something checked. What has to hold is
    not "the gate job exists" but "no job that names the environment can start before it", and
    that has to keep holding for the third such job nobody has written yet. Mutation (declared):
    point the gate's `ENVIRONMENT` at another name -> the equality below reddens, so the gate
    cannot end up checking a name no job uses.
    """
    jobs = _release_jobs()
    assert GATE_JOB in jobs, sorted(jobs)
    gated = {name: job["environment"] for name, job in jobs.items() if "environment" in job}
    # The non-vacuity guard: a walk that found no `environment:` at all would satisfy every
    # assertion below by having nothing to check.
    assert len(gated) >= 2, gated
    assert set(gated.values()) == {_gate_environment()}, (gated, _gate_environment())
    for name in gated:
        assert GATE_JOB in jobs[name].get("needs", ""), (name, jobs[name])
    # And the gate itself is not behind the environment it is asking about: it has to run in
    # the one case the environment asks nobody, which is the case it exists for.
    assert "environment" not in jobs[GATE_JOB], jobs[GATE_JOB]


def _run_gate(tmp_path: Path, gh: str, declared: str = "") -> tuple[int, str]:
    """The shipped gate script, out of the shipped file, against a `gh` that answers `gh`."""
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "gh").write_text(f"#!/bin/sh\n{gh}\n", encoding="utf-8")
    (stub / "gh").chmod(0o755)
    done = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step_script(RELEASE_WORKFLOW, GATE_STEP)],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{stub}:/usr/bin:/bin",
            "GH_TOKEN": "t",
            "REPOSITORY": "owner/repository",
            "ENVIRONMENT": _gate_environment(),
            "DECLARED": declared,
        },
    )
    return done.returncode, done.stdout + done.stderr


@needs_bash
@needs_release_workflow
@pytest.mark.parametrize(
    ("gh", "declared", "code", "wanted"),
    [
        ("echo 2", "", 0, "2 protection rule(s)"),
        # The case the gate exists for: GitHub made the environment up on the spot.
        ("echo 0", "", 1, "no protection rules"),
        ("echo 0", "true", 1, "no protection rules"),
        # Unreadable — an endpoint the default token may not be allowed, or no `gh` at all.
        ("echo denied >&2; exit 1", "", 1, "could not be read"),
        ("echo denied >&2; exit 1", "true", 0, "stands in for the read"),
        ("echo denied >&2; exit 1", "false", 1, "could not be read"),
        # A body that is not a count is not a count, and `[ "$x" -eq 0 ]` would have died on it.
        ("echo null", "", 1, "could not be read"),
    ],
    ids=["two-rules", "no-rules", "no-rules-declared", "unreadable", "declared", "denied", "null"],
)
def test_the_gate_admits_a_release_only_where_the_environment_is_one(
    tmp_path: Path, gh: str, declared: str, code: int, wanted: str
) -> None:
    """Nothing here can run GitHub Actions, so the script is run instead, exactly as shipped.

    The two rows that matter are `no-rules-declared` and `declared`, and they are the whole of
    what the repository variable is allowed to do: it stands in for the **read** when the
    endpoint is closed to the token, and it does not answer for an environment that read back
    with zero rules. Mutations (declared): stop testing the count for zero; let the variable be
    consulted before the read has failed.
    """
    got, printed = _run_gate(tmp_path, gh, declared)
    assert got == code, (got, printed)
    assert wanted in printed, printed
