"""No gate reads a key the tighten-only rule calls `neutral`.

The rule lets a pull request change `keelline.preset`, `keelline.profile`, `keelline.agents` and
`project.name` whatever the base enforces, on the ground that no gate reads them. That ground is
a fact about the gates, so it is executed rather than asserted: every built-in gate runs over a
clone once under the loaded configuration and once per neutral key moved, and must answer the
same. The unchanged run has a finding, so "the same" is not two empty answers.

No mutation of the rule reaches this, because the rule is not what it checks: the gates are. To
watch it fail, make `keelline.docs.hygiene.docs_gate` return `[]` when
`config.project.name == "gadget"`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import keelline
from keelline.assess.gates import GateContext, run_gates
from keelline.config.loader import load
from keelline.config.schema import BUILTIN_GATES, Config
from tests.assess.baserepo import AGENTS, clone, commit
from tests.gitfixture import git, needs_git

pytestmark = needs_git

# `AGENTS` is five lines, so it breaks this budget and the `docs` gate has a finding.
BASE = f"""[keelline]
version = "{keelline.__version__}"
state = "initialised"

[project]
name = "widget"

[budgets]
agents_md_lines = 3
"""
# The keys `tests/assess/test_rule.py` holds to `neutral` whatever the base enforces.
NEUTRAL = ("keelline.preset", "keelline.profile", "keelline.agents", "project.name")


def _moved(config: Config, key: str) -> Config:
    if key == "keelline.preset":
        return replace(config, keelline=replace(config.keelline, preset="other"))
    if key == "keelline.profile":
        return replace(config, keelline=replace(config.keelline, profile="python"))
    if key == "keelline.agents":
        return replace(config, keelline=replace(config.keelline, agents=("codex",)))
    assert key == "project.name"
    return replace(config, project=replace(config.project, name="gadget"))


@pytest.mark.parametrize("key", NEUTRAL)
def test_no_gate_reads_a_key_the_rule_calls_neutral(key: str, tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    (project / "AGENTS.md").write_text(f"{AGENTS}- Changed.\n", encoding="utf-8")
    commit(project, "docs: say what changed")
    base = git(project, "rev-parse", "refs/remotes/origin/main").strip()
    config = load(project, machine=tmp_path / "absent.toml")

    unchanged = run_gates(GateContext(project, config, base), BUILTIN_GATES)
    moved = run_gates(GateContext(project, _moved(config, key), base), BUILTIN_GATES)

    assert any(result.findings for result in unchanged)
    assert moved == unchanged
