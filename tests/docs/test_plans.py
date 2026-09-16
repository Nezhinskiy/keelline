"""Contracts for the plan lint: references resolve, steps are non-leading, mutation outcomes are
expectations, Scope/Premise are present. keelline:ledger:fixtures — `BR-` strings here are
sample data.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from keelline.config.loader import load
from keelline.config.schema import Config
from keelline.docs.plans import asserted_outcomes, lint

CONFIG = """
[keelline]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"
"""
SCOPE = "**Scope:** a change belongs to this branch iff it touches the widget.\n\n"

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def git(root: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(root.parent),
    }
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout


def project(tmp_path: Path) -> tuple[Path, Config]:
    root = tmp_path / "widget"
    (root / "docs" / "plans").mkdir(parents=True)
    (root / "keelline.toml").write_text(CONFIG, encoding="utf-8")
    return root, load(root, machine=tmp_path / "m.toml")


def plan(root: Path, body: str, name: str = "2026-01-01-x.md") -> Path:
    path = root / "docs" / "plans" / name
    path.write_text(body, encoding="utf-8")
    return path


def rules(root: Path, config: Config, *paths: Path) -> list[str]:
    return [f.rule for f in lint(root, config, plans=list(paths)).findings]


def test_an_unresolvable_reference_fails_and_a_resolvable_or_created_one_passes(
    tmp_path: Path,
) -> None:
    root, config = project(tmp_path)
    (root / "src").mkdir()
    (root / "src" / "ok.py").write_text("", encoding="utf-8")
    path = plan(
        root,
        SCOPE + "- Modify: `src/gone.py`\n- Modify: `src/ok.py`\n- Create: `src/new.py`\n"
        "later `src/new.py` (create)\n",
    )
    found = lint(root, config, plans=[path]).findings
    assert [(f.rule, f.line, f.detail) for f in found] == [("dead-reference", 3, "src/gone.py")]


def test_a_reference_inside_a_fence_is_fixture_text(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    path = plan(root, SCOPE + "```\n`src/gone.py`\n```\n")
    assert rules(root, config, path) == []


@pytest.mark.parametrize(
    "step",
    [
        "confirm that nothing bounds X",
        "verify nothing is logged",
        "check that no row exists",
        "Confirm it does not raise",
    ],
)
def test_a_leading_verification_step_fails(tmp_path: Path, step: str) -> None:
    root, config = project(tmp_path)
    assert rules(root, config, plan(root, SCOPE + f"- {step}\n")) == ["leading-step"]


def test_a_hyphenated_no_op_step_passes(tmp_path: Path) -> None:
    # `no(?!-)`: a hyphen is a word boundary, so plain `\bno\b` flags `no-op`. Mutation: drop
    # the lookahead — this reddens.
    root, config = project(tmp_path)
    assert rules(root, config, plan(root, SCOPE + "- verify no-op handling stays\n")) == []


def test_a_plan_without_a_scope_line_fails_and_a_bare_marker_does_not_count(
    tmp_path: Path,
) -> None:
    root, config = project(tmp_path)
    assert rules(root, config, plan(root, "no scope here\n")) == ["scope-missing"]
    assert rules(root, config, plan(root, "**Scope:**\n\nlater text\n")) == ["scope-missing"]
    assert rules(root, config, plan(root, "```\n**Scope:** in a fence\n```\n")) == ["scope-missing"]


def test_a_fixes_claim_needs_a_premise_line_with_content(tmp_path: Path) -> None:
    # The prefix comes from `[ledger] id_prefix`. Mutation: replace `[^\S\n]*\S` with `\s*\S`
    # in the premise rule — the bare-marker case reddens.
    root, config = project(tmp_path)
    assert rules(root, config, plan(root, SCOPE + "Fixes BR-042.\n")) == ["premise-missing"]
    assert rules(root, config, plan(root, SCOPE + "Fixes BR-042.\n\n**Premise:**\n\nlater\n")) == [
        "premise-missing"
    ]
    assert (
        rules(
            root, config, plan(root, SCOPE + "Fixes BR-042.\n\n**Premise (entry):** X says so.\n")
        )
        == []
    )
    assert rules(root, config, plan(root, SCOPE + "```\nFixes BR-042\n```\n")) == []


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        ("Remove the guard -> the test reddens.", True),
        ("Watch the fail-closed test go red under that mutation.", True),
        ("Verify it stays green if the clone step is dropped.", True),
        ("The change reddens **8 assertions** in the module.", True),
        (
            "Expected: removing the guard -> the test reddens; if it reddens for another "
            "reason redesign it.",
            False,
        ),
        ("Removing the guard -> the test reddened, alone.", False),
        ("Run the test to verify it fails.", False),
        (
            "Data flows a -> b -> c, and very much later in this deliberately long and winding "
            "sentence the structural check must stay green.",
            False,
        ),
    ],
)
def test_an_asserted_mutation_outcome_is_a_finding_unless_marked_or_reported(
    text: str, flagged: bool
) -> None:
    assert (asserted_outcomes(text + "\n") != []) is flagged


def test_a_claim_split_across_a_wrap_is_still_one_sentence(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    path = plan(
        root,
        SCOPE + "Drop the guard ->\nthe test reddens.\n\n"
        "**Expected:** dropping the other guard ->\nit reddens.\n",
    )
    found = lint(root, config, plans=[path]).findings
    assert [(f.rule, f.line) for f in found] == [("asserted-outcome", 3)]


def test_a_finding_after_a_fence_reports_the_files_own_line(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    path = plan(root, SCOPE + "```\n1\n2\n3\n```\n- `src/gone.py`\n")
    assert [f.line for f in lint(root, config, plans=[path]).findings] == [8]


@needs_git
def test_without_paths_only_the_plans_the_diff_touches_are_linted(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    git(root, "init", "-q", "-b", "main")
    old = plan(root, "no scope, but committed on the base\n", "2026-01-01-old.md")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "seed")
    git(root, "remote", "add", "origin", str(root))  # the base ref resolves to the seed
    git(root, "fetch", "-q", "origin")
    git(root, "checkout", "-qb", "feature")
    new = plan(root, "no scope either\n", "2026-01-02-new.md")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "new plan")
    result = lint(root, config, plans=[])
    assert result.linted == [new] and old not in result.linted
    assert [f.rule for f in result.findings] == ["scope-missing"]


@needs_git
def test_a_base_that_will_not_resolve_is_a_finding_not_an_ok(tmp_path: Path) -> None:
    # This gate ran green for its whole life on a shallow checkout that had no base ref.
    # Mutation: return an empty finding list when `touched_plans` is None — this reddens.
    root, config = project(tmp_path)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "seed")
    result = lint(root, config, plans=[])
    assert [f.rule for f in result.findings] == ["base-unresolvable"] and result.linted == []


@needs_git
def test_an_uncommitted_plan_is_reported_as_unlinted_and_linted_when_named(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "seed")
    git(root, "remote", "add", "origin", str(root))
    git(root, "fetch", "-q", "origin")
    draft = plan(root, "a draft with a space in it\n", "2026-01-03-a draft.md")
    result = lint(root, config, plans=[])
    assert result.unlinted == [draft] and result.linted == []
    named = lint(root, config, plans=[draft])
    assert named.linted == [draft] and [f.rule for f in named.findings] == ["scope-missing"]


def test_a_named_plan_that_does_not_exist_is_a_failure(tmp_path: Path) -> None:
    from keelline.errors import Failure

    root, config = project(tmp_path)
    with pytest.raises(Failure):
        lint(root, config, plans=[root / "docs" / "plans" / "missing.md"])
