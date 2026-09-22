"""The twelve shipped files, and the `Template` list a configuration produces from them."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from keelline.attach.api import IGNORE_BODY, IGNORE_REGION
from keelline.config.loader import preset_defaults
from keelline.config.schema import Config
from keelline.errors import Failure, Refusal
from keelline.ledger.api import render_index
from keelline.project.api import PROJECT_FILES, Prepared, project_templates
from keelline.project.templates import PATH_KEYS, fill, read
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


def test_no_two_artifacts_of_one_pass_resolve_to_the_same_file(tmp_path: Path) -> None:
    """DC3's premise, which nothing made true until now.

    `scaffold.engine.plan` has no duplicate-target detection and C2 is frozen, so with two
    `[paths]` keys aimed at one file both plans reported zero refusals, `apply` wrote both, the
    file held only the second artifact's bytes, and the manifest recorded two different `sha256`
    values for one target. Measured on this tree before the guard, with
    `paths.roadmap = paths.roadmap_history = "docs/x.md"`: `refusals: 0 0`, the manifest held a
    record for `roadmap` and one for `roadmap-history` both naming `docs/x.md` and carrying
    different `sha256` values, the file began `# Roadmap history`, and `"Design and plan trail" in
    body` was `False`. (The two digests are not quoted here: `tests/test_neutral.py`'s
    bare-commit-id arm reads an eight-character hex run as an abbreviated commit id, and it is
    right to — measured, this docstring reddened that gate on its first draft.)

    Both passes, because the write-once pass collides too — `paths.agents_md = "CLAUDE.md"` puts
    the skeleton and the pointer on one file.

    Mutation (oracle): drop the footprint pass's check -> the roadmap case reddens.
    """
    config = preset_defaults("widget")
    footprint_clash = replace(
        config, paths=replace(config.paths, roadmap="docs/x.md", roadmap_history="docs/x.md")
    )
    with pytest.raises(Refusal) as caught:
        _prepared(footprint_clash, root=tmp_path)
    message = str(caught.value)
    assert "roadmap (paths.roadmap)" in message and "roadmap-history" in message
    assert "paths.roadmap_history" in message
    # The colliding value is the repository's own bytes and is named nowhere.
    assert "docs/x.md" not in message

    once_clash = replace(config, paths=replace(config.paths, agents_md="CLAUDE.md"))
    with pytest.raises(Refusal, match=r"claude-md|agents-skeleton"):
        _prepared(once_clash, root=tmp_path)


def test_every_artifact_both_passes_build_has_a_paths_key_recorded_for_it() -> None:
    """The anti-drift half of `PATH_KEYS`: an artifact added without a line there would reach a
    `KeyError` only once somebody's configuration happened to collide, which is the worst moment
    for this module to raise something other than its own refusal."""
    config = _recording(preset_defaults("widget"))
    prepared = project_templates(
        Path("/nonexistent/root"), config, resolution=PINNED, document=DOCUMENT
    )
    ids = {t.id for t in (*prepared.once, *prepared.footprint)}
    # The walk is stated non-empty first, and at its full size: a `Prepared` that built nothing
    # would make the comparison below vacuous in both directions.
    assert len(ids) == 16, sorted(ids)
    assert ids == set(PATH_KEYS), (sorted(ids ^ set(PATH_KEYS)),)


def test_a_template_sentinel_left_unfilled_costs_the_artifact_rather_than_shipping() -> None:
    """`fill` refuses text still carrying a `%%KEY%%`, and nothing proved it did.

    Measured: with `left = _SENTINEL.search(text)` replaced by `left = None`, `tests/project`
    was 39 passed — so the guard whose absence puts `check.yml@%%SHA%%` into an adopting
    project's CI, and `# %%NAME%%` at the head of the file every session loads, was executed by
    the suite and asserted by none of it.

    The sentinel's own name prints: it is a string from a template this package ships, which is
    Keelline's own text and not a repository's.

    Mutation (oracle): the search is made to answer `None` -> the first assertion reddens.
    """
    assert fill("a %%ONE%% b", ONE="1") == "a 1 b"
    with pytest.raises(Failure, match=re.escape("%%SHA%%")):
        fill("uses: x/check.yml@%%SHA%%")
    # Filling one and leaving the other is the real shape of the fault: a `fill` call that has
    # grown a sentinel its caller does not pass yet.
    with pytest.raises(Failure, match=re.escape("%%GATE_BRANCH%%")):
        fill("@%%SHA%% on %%GATE_BRANCH%%", SHA="a" * 40)


def test_read_refuses_a_name_this_package_does_not_ship_before_it_joins_it() -> None:
    """The containment check in `read`, which nothing proved either.

    Measured: with `if name not in PROJECT_FILES:` replaced by `if False:`, `tests/project` was
    39 passed. The anchor is `PROJECT_FILES` — a constant in the wheel beside the files it names
    — and the party contained is a caller inside this package, which is why the check is before
    the join and not after: `name` decides which file under the tree is opened.

    Mutation (oracle): the membership check is dropped -> the traversal name reaches
    `read_text` and raises `OSError` instead of this module's own `Failure`.
    """
    for name in ("../../../etc/passwd", "keelline.toml", ".", ""):
        with pytest.raises(Failure, match="is not a shipped project template"):
            read(name)
    # And a name it does ship is read, so the check is not simply refusing everything.
    assert read("claude.md") == "@AGENTS.md\n"
