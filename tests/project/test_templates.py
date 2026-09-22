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


def _recording(config: Config, ref: str = SHA) -> Config:
    """`config` with `[ci] ref` set, which is the only thing that renders a workflow.

    The workflow is built from what `keelline.toml` will say on disk and never from the
    resolution, so a test that wants one says so on the configuration rather than on the pin.
    """
    return replace(config, ci=replace(config.ci, ref=ref))


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


def test_the_ci_workflow_is_offered_only_with_a_recorded_ref_and_says_why_otherwise(
    tmp_path: Path,
) -> None:
    # Mutation (oracle): `if resolution.pin is None:` -> `if False:` -> the "no released tag"
    # arm falls through to `NO_REF` and the second assertion reddens. The workflow is still not
    # offered, because what renders one is `[ci] ref` and there is none.
    config = preset_defaults("widget")
    assert "ci-workflow" not in {t.id for t in _prepared(config, root=tmp_path).footprint}
    assert (
        _prepared(config, root=tmp_path)
        .skipped["ci-workflow"]
        .startswith("no released Keelline tag")
    )
    skipped = _prepared(config, resolution=Resolution(None, False), root=tmp_path).skipped
    assert "could not be asked" in skipped["ci-workflow"]
    # A pin resolved and the document records no ref: the adoption path, where nothing this run
    # resolved reaches the file. No workflow, and the reason says which of the three it is.
    no_ref = _prepared(config, resolution=PINNED, root=tmp_path)
    assert "ci-workflow" not in {t.id for t in no_ref.footprint}
    assert no_ref.skipped["ci-workflow"].startswith("the keelline.toml this repository already")
    footprint = _prepared(_recording(config), resolution=PINNED, root=tmp_path).footprint
    body = {t.id: t for t in footprint}["ci-workflow"].render()
    assert f"/.github/workflows/check.yml@{SHA} # v0.1.0" in body and "%%" not in body
    assert 'branches: ["main"]' in body
    for mode, phrase in (("none", "[ci] mode is none"), ("uvx", "ships with a later lane")):
        varied = replace(_recording(config), ci=replace(_recording(config).ci, mode=mode))
        prepared = _prepared(varied, resolution=PINNED, root=tmp_path)
        assert phrase in prepared.skipped["ci-workflow"], mode
    # The hostile arm is reached AFTER a ref is in hand, which is why the skip reason matters as
    # much as the missing artifact: `commands.py` used to key its CI line on the pin, so this
    # state printed `CI: <tag>@<sha>` for a run that planned no workflow. `skipped` is what the
    # command reads now, so this asserts the key is there and says why.
    recorded = _recording(config)
    hostile = replace(recorded, ci=replace(recorded.ci, gate_branch="main'; rm -rf"))
    pinned_hostile = _prepared(hostile, resolution=PINNED, root=tmp_path)
    assert "ci-workflow" not in {t.id for t in pinned_hostile.footprint}
    assert pinned_hostile.skipped["ci-workflow"] == (
        "[ci] gate_branch is not a plain branch name, so no workflow was rendered around it"
    )
    assert "rm -rf" not in pinned_hostile.skipped["ci-workflow"]


def test_a_recorded_ref_outside_the_grammar_is_never_rendered_into_the_uses_line(
    tmp_path: Path,
) -> None:
    """`[ci] ref` is repository-authored and lands in a YAML file GitHub executes.

    On the adoption path it is whatever `keelline.toml` already carried, and the loader bounds it
    to "a string" and nothing more — so it is held to `CI_REF` before it is written, exactly as
    `gate_branch` is held to `GATE_BRANCH`, and a value outside the grammar costs the artifact
    rather than the run. The anchor is `CI_REF`, a constant in the installed package that nothing
    a repository writes can move.

    Mutation (oracle): drop the `CI_REF` check -> the hostile ref is rendered into the `uses:`
    line and the first assertion of that case reddens.
    """
    config = preset_defaults("widget")
    for ref in ("main'; rm -rf", "abc", SHA.upper(), f"{SHA}\n"):
        prepared = _prepared(_recording(config, ref), resolution=PINNED, root=tmp_path)
        assert "ci-workflow" not in {t.id for t in prepared.footprint}, ref
        assert prepared.skipped["ci-workflow"].startswith("[ci] ref is not a full-length"), ref
        # The value itself is never echoed: the reason names the key and the shape, the way
        # `gate_branch`'s does. Checked apart from the loop below, whose value the fixed text
        # legitimately names.
        assert ref not in prepared.skipped["ci-workflow"], ref
    # The documented mutable alias is refused too, and for a different reason than a hostile
    # value: `v1` is a ref GitHub would accept and `doctor` reports as a mutable opt-in, and
    # `docs/cli.md` says it is a file a project writes by hand. `init` renders immutable pins.
    alias = _prepared(_recording(config, "v1"), resolution=PINNED, root=tmp_path)
    assert "ci-workflow" not in {t.id for t in alias.footprint}
    assert alias.skipped["ci-workflow"].startswith("[ci] ref is not a full-length")


def test_a_ref_this_run_did_not_resolve_is_pinned_without_claiming_a_release(
    tmp_path: Path,
) -> None:
    # The adoption path's rendered workflow. The `uses:` ref is the document's own, and the
    # trailing comment says where it came from rather than naming a release the file does not
    # record — a `# v0.1.0` beside somebody else's commit is an assertion this build cannot make.
    other = "d" * 40
    footprint = _prepared(
        _recording(preset_defaults("widget"), other), resolution=PINNED, root=tmp_path
    ).footprint
    body = {t.id: t for t in footprint}["ci-workflow"].render()
    assert f"/.github/workflows/check.yml@{other} # from [ci] ref" in body
    assert "v0.1.0" not in body and SHA not in body


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
    prepared = _prepared(_recording(preset_defaults("widget")), resolution=PINNED, root=tmp_path)
    body = {t.id: t for t in prepared.footprint}["ci-workflow"].render()
    passed = set(re.findall(r"^      ([a-z-]+): ", body, re.MULTILINE))
    assert passed and passed <= declared, (passed, declared)
