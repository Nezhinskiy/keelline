"""The inventory `keelline assess` writes: every configured gate over the smoke fixture, each
gate finding as an item, the one serialisation, and a summary that prints counts and never a
path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keelline.assess.assessment import (
    FORMAT,
    NOT_IGNORED,
    assess,
    document,
    ignored,
    render,
    write,
)
from keelline.assess.gates import BUILTIN
from keelline.attach.api import IGNORE_BODY
from keelline.cli import build_parser, discover_registrars, run
from keelline.project.api import ASSESSMENT
from tests.assess.smoke import BASE, smoke_repo
from tests.gitfixture import git, needs_git

# One word a line, so the file is over the line budget and nothing else a word could trip.
OVER_BUDGET = "".join("word\n" for _ in range(400))


def _machine(tmp_path: Path) -> Path:
    return tmp_path / "m.toml"


def _over_budget(tmp_path: Path) -> Path:
    """The smoke copy with its `AGENTS.md` replaced by 400 one-word lines."""
    root = smoke_repo(tmp_path)
    (root / "AGENTS.md").write_text(OVER_BUDGET, encoding="utf-8")
    return root


@needs_git
def test_the_smoke_fixture_would_fail_no_gate(tmp_path: Path) -> None:
    # The closing criterion: against `BASE` every built-in judges something, and none fails.
    # No mutation of its own — each gate's finding cases hold that gate.
    root = smoke_repo(tmp_path)
    assessment = assess(root, machine=_machine(tmp_path), base=BASE)
    assert assessment.would_fail == ()
    assert tuple(g.name for g in assessment.gates) == tuple(g.name for g in BUILTIN)


@needs_git
def test_the_inventory_records_its_base_and_lands_where_git_ignores_it(tmp_path: Path) -> None:
    # Mutation: drop the `"base"` key from `document` -> the tuple below reddens on a KeyError.
    root = smoke_repo(tmp_path)
    assessment = assess(root, machine=_machine(tmp_path), base=BASE)
    write(root, assessment)
    written = json.loads((root / ASSESSMENT).read_text(encoding="utf-8"))
    assert written == json.loads(json.dumps(document(assessment)))
    assert (written["format"], written["base"], len(written["gates"])) == (FORMAT, BASE, 5)
    assert git(root, "check-ignore", "--", ASSESSMENT).strip() == ASSESSMENT


def test_the_ignore_region_keeps_the_inventory_out_of_git() -> None:
    # Mutation: drop the inventory's entry from `attach.write.IGNORED` -> reddens.
    assert ASSESSMENT in IGNORE_BODY.splitlines()


@needs_git
def test_a_gate_finding_is_an_item_with_the_gate_s_rule_and_remedy(tmp_path: Path) -> None:
    # Mutation: `items = [i for r in results ...]` becomes `items = []` in `assess` -> the
    # comprehension below finds nothing and the equality reddens.
    root = _over_budget(tmp_path)
    assessment = assess(root, machine=_machine(tmp_path), base=BASE)
    docs = next(g for g in BUILTIN if g.name == "docs")
    found = [i for i in assessment.items if i.rule == "agents-lines"]
    assert [(i.probe, i.count, i.where) for i in found] == [
        ("docs", 1, ("AGENTS.md [agents-lines]",))
    ]
    assert found[0].remedy == docs.remedy


@needs_git
def test_the_summary_prints_counts_and_never_a_path(tmp_path: Path) -> None:
    # Declared in `mutations.toml`: the gate table's count cell printing each finding's path.
    root = _over_budget(tmp_path)
    summary = render(assess(root, machine=_machine(tmp_path), base=BASE))
    lines = summary.splitlines()
    assert "| docs | yes | 2 | yes |" in lines
    assert [line for line in lines if line.startswith("| docs | agents-lines | warning | 1 |")]
    assert "AGENTS.md" not in summary


@needs_git
def test_an_inventory_git_does_not_ignore_is_named_in_the_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Mutation: drop the `ignored(root) is False` branch in `run_assess` -> the last line is the
    # table's and the first assertion on the summary reddens.
    parser = build_parser(discover_registrars())
    kept = smoke_repo(tmp_path / "kept")
    bare = smoke_repo(tmp_path / "bare")
    (bare / ".gitignore").unlink()
    git(bare, "commit", "-qam", "chore: no ignore region")
    summaries = {}
    for name, root in (("kept", kept), ("bare", bare)):
        argv = ["assess", "--root", str(root), "--machine", str(_machine(tmp_path)), "--base", BASE]
        assert run([*argv, "--json"], parser=parser) == 0
        summaries[name] = json.loads(capsys.readouterr().out)["summary"]
    assert ignored(bare) is False
    assert summaries["bare"].splitlines()[-1] == NOT_IGNORED
    assert ignored(kept) is True
    assert NOT_IGNORED not in summaries["kept"]
