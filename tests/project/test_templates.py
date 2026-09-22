"""The twelve shipped files, and the `Template` list a configuration produces from them."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from keelline.attach.api import IGNORE_BODY, IGNORE_REGION
from keelline.config.loader import preset_defaults
from keelline.config.schema import Config
from keelline.ledger.api import render_index
from keelline.project.api import PROJECT_FILES, Prepared, project_templates
from keelline.release.api import Pin, Resolution
from keelline.scaffold import Kind, Style
from keelline.templates import tree

SHA = "a" * 40
DOCUMENT = '[keelline]\nversion = "0.1.0"\n\n[project]\nname = "widget"\n'
ROOT = Path(__file__).resolve().parents[2]
CHECK_WORKFLOW = ROOT / ".github" / "workflows" / "check.yml"
NO_PIN = Resolution(None, True)
PINNED = Resolution(Pin("v0.1.0", SHA), True)


def _prepared(
    config: Config, *, resolution: Resolution = NO_PIN, root: Path = Path("/nonexistent/root")
) -> Prepared:
    return project_templates(root, config, resolution=resolution, document=DOCUMENT)


def test_every_declared_file_exists_and_no_file_is_undeclared_at_any_depth() -> None:
    # `rglob`, not `iterdir`: a stray file in a subdirectory would ship in the wheel unseen.
    root = tree("project")
    assert root.is_dir()
    present = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    assert present == sorted(PROJECT_FILES)


def test_the_three_write_once_artifacts_are_once_and_the_rest_are_not(tmp_path: Path) -> None:
    prepared = _prepared(preset_defaults("widget"), root=tmp_path)
    assert [t.id for t in prepared.once] == ["config", "agents-skeleton", "claude-md"]
    assert all(t.kind is Kind.ONCE for t in prepared.once)
    assert {t.id: t.render() for t in prepared.once}["config"] == DOCUMENT
    assert "# widget" in {t.id: t.render() for t in prepared.once}["agents-skeleton"]
    assert not any(t.kind is Kind.ONCE for t in prepared.footprint)


def test_targets_follow_the_configured_paths_and_not_the_preset(tmp_path: Path) -> None:
    config = preset_defaults("widget")
    moved = replace(
        config,
        paths=replace(
            config.paths,
            specs="docs/design/specs",
            plans="docs/design/plans",
            roadmap="docs/plan/roadmap.md",
        ),
    )
    by_id = {t.id: t for t in _prepared(moved, root=tmp_path).footprint}
    assert by_id["specs-keep"].target == "docs/design/specs/.gitkeep"
    assert by_id["trail"].target == "docs/plan/trail.toml"
    assert by_id["gitignore"].kind is Kind.MANAGED_REGION
    assert by_id["gitignore"].region == IGNORE_REGION
    assert by_id["gitignore"].style is Style.HASH and by_id["gitignore"].render() == IGNORE_BODY
    assert by_id["agents-md"].region == "harness"
    assert "docs/plan/roadmap.md" in by_id["agents-md"].render()
    assert by_id["bug-index"].render() == render_index([], moved)


def test_the_ci_workflow_is_offered_only_with_a_pin_and_says_why_otherwise(tmp_path: Path) -> None:
    # Mutation (oracle): `if resolution.pin is None:` -> `if False:` -> the workflow is offered
    # with no pin and the first assertion reddens; rendered, its `uses:` would carry `@` and
    # nothing, which `actions/checkout` reads as the default branch.
    config = preset_defaults("widget")
    assert "ci-workflow" not in {t.id for t in _prepared(config, root=tmp_path).footprint}
    assert (
        _prepared(config, root=tmp_path)
        .skipped["ci-workflow"]
        .startswith("no released Keelline tag")
    )
    skipped = _prepared(config, resolution=Resolution(None, False), root=tmp_path).skipped
    assert "could not be asked" in skipped["ci-workflow"]
    footprint = _prepared(config, resolution=PINNED, root=tmp_path).footprint
    body = {t.id: t for t in footprint}["ci-workflow"].render()
    assert f"/.github/workflows/check.yml@{SHA} # v0.1.0" in body and "%%" not in body
    assert 'branches: ["main"]' in body
    for mode, phrase in (("none", "[ci] mode is none"), ("uvx", "ships with a later lane")):
        varied = replace(config, ci=replace(config.ci, mode=mode))
        prepared = _prepared(varied, resolution=PINNED, root=tmp_path)
        assert phrase in prepared.skipped["ci-workflow"], mode
    hostile = replace(config, ci=replace(config.ci, gate_branch="main'; rm -rf"))
    hostile_ids = {t.id for t in _prepared(hostile, resolution=PINNED, root=tmp_path).footprint}
    assert "ci-workflow" not in hostile_ids


def test_the_rendered_workflow_passes_only_inputs_the_reusable_workflow_declares(
    tmp_path: Path,
) -> None:
    # Held to the code, not a second spelling: if `check.yml` renames an input, every adopting
    # project's CI breaks and nothing here would notice. Both files are read as text — the
    # runtime and this suite are stdlib-only, so there is no YAML parser to reach for — with the
    # same indentation the two files actually use.
    declared = set(
        re.findall(r"^      ([a-z-]+):$", CHECK_WORKFLOW.read_text(encoding="utf-8"), re.MULTILINE)
    )
    footprint = _prepared(preset_defaults("widget"), resolution=PINNED, root=tmp_path).footprint
    body = {t.id: t for t in footprint}["ci-workflow"].render()
    passed = set(re.findall(r"^      ([a-z-]+): ", body, re.MULTILINE))
    assert passed and passed <= declared, (passed, declared)
