"""The twelve shipped files, and the `Template` list a configuration produces from them."""

from __future__ import annotations

import re
from dataclasses import replace
from importlib import resources
from pathlib import Path

import pytest

from keelline.attach.api import IGNORE_BODY, IGNORE_REGION
from keelline.config.loader import preset_defaults
from keelline.config.schema import Config
from keelline.errors import Failure, Refusal
from keelline.harnesses import HARNESSES
from keelline.ledger.api import render_index
from keelline.profiles import load_profile
from keelline.project.api import PROJECT_FILES, Prepared, project_templates
from keelline.project.templates import (
    COMPUTED,
    LOCAL_PROFILE,
    NO_REF,
    PATH_KEYS,
    PROFILE,
    PROJECT,
    fill,
    read,
    refuse_local_profile,
)
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
    config: Config,
    *,
    resolution: Resolution = NO_PIN,
    root: Path = Path("/nonexistent/root"),
    adopted: bool = False,
    dry_run: bool = False,
) -> Prepared:
    """This file's default is the run that *creates* `keelline.toml`, which is the path on which
    the three "why there is no ref" sentences are the answers. `adopted=True` is the other kind
    of run, and it has one answer; the case below holds that."""
    return project_templates(
        root, config, resolution=resolution, document=DOCUMENT, adopted=adopted, dry_run=dry_run
    )


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


def test_the_claude_md_pointer_names_the_configured_instruction_file(tmp_path: Path) -> None:
    """The rendered bytes, not the template's: the pointer is one line and that line is a path.

    `claude.md` shipped as the literal `@AGENTS.md` and was built with no `render` override, so
    `[paths] agents_md = "CONTEXT.md"` produced `CLAUDE.md` pointing at a file the run did not
    write, `CONTEXT.md` beside it, and a `keelline docs check` that passed — every Claude Code
    session in that project following a dangling pointer, with nothing anywhere saying so.

    Mutation (oracle): `AGENTS_MD=p.agents_md` -> `AGENTS_MD=CLAUDE_MD` -> the pointer names the
    pointer and the renamed case reddens. The self-pointer that mutation writes is the one
    `_one_target_each` already refuses when a repository asks for it, so this is the only way to
    reach it.
    """
    config = preset_defaults("widget")
    by_id = {t.id: t for t in _prepared(config, root=tmp_path).once}
    assert by_id["claude-md"].render() == "@AGENTS.md\n"
    moved = replace(config, paths=replace(config.paths, agents_md="CONTEXT.md"))
    renamed = {t.id: t for t in _prepared(moved, root=tmp_path).once}
    # The pointer and the file the skeleton is written to are one path, asserted together: a
    # pointer that merely changed would still be wrong if it named something else.
    assert renamed["claude-md"].render() == "@CONTEXT.md\n"
    assert renamed["agents-skeleton"].target == "CONTEXT.md"
    assert "%%" not in renamed["claude-md"].render()


def test_the_skeleton_states_the_budgets_this_project_will_be_held_to(tmp_path: Path) -> None:
    """The rendered bytes again, and the numbers are `Budgets.effective`'s and not the preset's.

    The three numbers were literals in the shipped template — 300, 3,000 and 50, the preset's
    own. A project that lowered `agents_md_lines` to 250 received a document Keelline wrote
    telling it 300 was fine, and `keelline docs check` then failed the same document at 251.
    Nothing held the literals to the preset, so nothing could see them drift either.

    Mutation (oracle): `LINES=_budget(config, "agents_md_lines")` ->
    `LINES=_budget(config, "agents_md_words")` -> the lowered case reddens.
    """
    config = preset_defaults("widget")
    body = {t.id: t for t in _prepared(config, root=tmp_path).once}["agents-skeleton"].render()
    assert "at most 300\nlines and 3,000 words" in body and "below at most 50 lines" in body
    # A project may lower a budget and never raise it (D7), so the rendered sentence follows the
    # override down and ignores it upward -- `effective`'s rule, read through the file that
    # states it. `agents_md_words` is left at the preset in the same case, so a fill that took
    # one number for all three cannot pass.
    lowered = replace(
        config,
        budgets=replace(config.budgets, configured={"agents_md_lines": 250, "status_lines": 999}),
    )
    body = {t.id: t for t in _prepared(lowered, root=tmp_path).once}["agents-skeleton"].render()
    assert "at most 250\nlines and 3,000 words" in body and "below at most 50 lines" in body
    assert "300" not in body and "999" not in body and "%%" not in body


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
    # A pin resolved and the document records no ref. On a run that creates the document this is
    # unreachable — `init` records the pin it resolved — so the case is stated on the adoption
    # path, where it is the ordinary one.
    no_ref = _prepared(config, resolution=PINNED, root=tmp_path, adopted=True)
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


def test_the_adoption_path_is_never_sent_to_the_network_for_a_file_it_must_edit(
    tmp_path: Path,
) -> None:
    """`_ci`'s own docstring states the rule, and the code had the inverse of it.

    `project_templates` took no adoption flag, so `_ci` saw only a `Resolution` and could not
    tell which kind of run it was in. Under the preset's `[ci] mode = "reusable"`, on a
    repository with a hand-written `keelline.toml` and no `[ci] ref` — the ordinary adoption
    path — an unreachable remote printed "run `keelline init --yes` again with the network
    reachable" and a pre-release Keelline printed "no released Keelline tag matches the version
    running". Neither is why there is no workflow, and running again cannot produce one:
    `keelline.toml` is a `Kind.ONCE` artifact already on disk, so no pin any run resolves is ever
    recorded and the workflow is skipped again, for ever.

    All three states are one answer here, and the same one. Asserted as the whole text and not a
    prefix, so a run that reached `NO_REF` through a different arm cannot pass for this.

    Mutation (oracle): `if adopted:` -> `if False:` -> the first two cases fall through to the
    resolution's own arms and redden.
    """
    config = preset_defaults("widget")
    for resolution in (Resolution(None, False), NO_PIN, PINNED):
        prepared = _prepared(config, resolution=resolution, root=tmp_path, adopted=True)
        assert "ci-workflow" not in {t.id for t in prepared.footprint}, resolution
        assert prepared.skipped["ci-workflow"] == NO_REF, resolution
    # And the network's own answers still print on the run that creates the document, which is
    # the only run they are the reason for: a pin written there does reach the file.
    assert (
        "could not be asked"
        in _prepared(config, resolution=Resolution(None, False), root=tmp_path).skipped[
            "ci-workflow"
        ]
    )
    assert _prepared(config, root=tmp_path).skipped["ci-workflow"].startswith("no released")


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
    prepared = project_templates(
        Path("/nonexistent/root"),
        _python(tuple(h.name for h in HARNESSES)),
        resolution=PINNED,
        document=DOCUMENT,
        adopted=False,
        dry_run=False,
    )
    ids = {t.id for t in (*prepared.once, *prepared.footprint)}
    # The walk is stated non-empty first, and at its full size: a `Prepared` that built nothing
    # would make the comparison below vacuous in both directions. A harness's rendition has no
    # row in `PATH_KEYS`; its id is asked of the registry, so a harness added there is covered
    # here with no edit.
    assert len(ids) == 17 + len(_renditions()), sorted(ids)
    expected = set(PATH_KEYS) | _renditions()
    assert ids == expected, (sorted(ids ^ expected),)


def test_every_source_both_passes_build_is_a_shipped_file_or_is_declared_computed() -> None:
    """The same anti-drift rule over `Template.source`, which had no guard and was wrong.

    `source` becomes `Record.template` in `.keelline/manifest.json` — committed, and what
    `upgrade` will read to find out where an artifact's bytes came from. Three artifacts recorded
    `project/config`, `project/bug-index` and `project/gitignore`: names `PROJECT_FILES` does not
    carry, that the wheel does not ship, and that `read` refuses by name. Nothing raised, because
    all three build their own bytes — but the provenance was a pointer at nothing, and the
    committed smoke fixture's manifest has carried `"template": "project/gitignore"` for as long
    as it has existed.

    Three rules: a source is `project/<a file the wheel ships>`; or it is
    `computed/<artifact id>` and this module or a harness builds the bytes; or it is
    `profile/<name>/<a file that profile ships>`.

    Mutation (oracle): `_computed`'s source is spelled `f"{PROJECT}/{artifact_id}"` -> the
    computed set's assertion reddens, and so does the fixture module's provenance assertion.
    """
    prepared = project_templates(
        Path("/nonexistent/root"),
        _python(tuple(h.name for h in HARNESSES)),
        resolution=PINNED,
        document=DOCUMENT,
        adopted=False,
        dry_run=False,
    )
    sources = {t.id: t.source for t in (*prepared.once, *prepared.footprint)}
    # Non-empty and at full size first, for `PATH_KEYS`' reason: nothing built makes every
    # comparison below true of nothing.
    assert len(sources) == 17 + len(_renditions()), sorted(sources)
    computed = {name for name, source in sources.items() if source.startswith(f"{COMPUTED}/")}
    # As the set and not as a count: an artifact that moved from one rule to the other is exactly
    # the drift this test exists to see, and a count would not see it.
    assert computed == {"config", "bug-index", "gitignore"} | _renditions()
    root = tree(PROJECT)
    for artifact_id, source in sources.items():
        if artifact_id in computed:
            assert source == f"{COMPUTED}/{artifact_id}"
            continue
        if source.startswith(f"{PROFILE}/"):
            _, name, file = source.split("/")
            assert (resources.files("keelline.profiles") / name / file).is_file(), source
            continue
        area, _, name = source.partition("/")
        assert area == PROJECT and name in PROJECT_FILES, source
        # And the name is a file that is really there: `project/<name>` claims the bytes were
        # read from the wheel, and the three names above could never have been read at all.
        assert (root / name).is_file(), source


def test_a_template_sentinel_left_unfilled_costs_the_artifact_rather_than_shipping() -> None:
    """`fill` refuses text still carrying a `%%KEY%%`, and nothing proved it did.

    Measured: with `left = _SENTINEL.search(text)` replaced by `left = None`, `tests/project`
    was 39 passed — so the guard whose absence puts `check.yml@%%REF%%` into an adopting
    project's CI (`%%REF%%` is the workflow template's own sentinel), and `# %%NAME%%` at the head
    of the file every session loads, was executed by the suite and asserted by none of it.

    The sentinel's own name prints: it is a string from a template this package ships, which is
    Keelline's own text and not a repository's. The names below are deliberately *not* ones this
    package ships — the subject is any unfilled sentinel, not the two real ones.

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
    assert read("claude.md") == "@%%AGENTS_MD%%\n"


def _python(agents: tuple[str, ...] = ("claude", "codex")) -> Config:
    config = _recording(preset_defaults("widget"))
    return replace(config, keelline=replace(config.keelline, profile="python", agents=agents))


def _renditions() -> set[str]:
    """Every harness rendition's artifact id, asked of the registry."""
    profile = load_profile("python")
    return {
        h.render_profile(profile, "rules.md").artifact_id
        for h in HARNESSES
        if h.render_profile is not None
    }


def test_a_profile_lands_once_neutrally_and_once_per_adapted_harness(tmp_path: Path) -> None:
    by_id = {t.id: t for t in _prepared(_python(), root=tmp_path).footprint}
    assert by_id["profile-rules"].target == "docs/keelline/rules/python.md"
    assert by_id["profile-rules"].source == "profile/python/rules.md"
    assert by_id["profile-rules"].render() == load_profile("python").rules
    assert by_id["claude-rules"].target == ".claude/rules/keelline-python.md"
    assert by_id["claude-rules"].source == "computed/claude-rules"
    assert "`docs/keelline/rules/python.md`" in by_id["claude-rules"].render()


def test_a_harness_not_listed_gets_no_file_of_its_own(tmp_path: Path) -> None:
    ids = {t.id for t in _prepared(_python(agents=("codex",)), root=tmp_path).footprint}
    assert "profile-rules" in ids and "claude-rules" not in ids


def test_a_profile_artifact_kept_out_of_git_is_refused(tmp_path: Path) -> None:
    """The `AGENTS.md` pointer and the Claude rule read `profile-rules` at its committed path;
    kept local it lands under `.keelline/local/artifacts/`, and both point at nothing (a review
    reproduced all three files). Mutation (declared): the refusal's condition dropped -> this
    reddens.
    """
    config = _python()
    refuse_local_profile(_prepared(config, root=tmp_path), config)
    for local in (("profile-rules",), ("claude-rules",), ("profile-rules", "roadmap")):
        kept = replace(config, artifacts=replace(config.artifacts, local=local))
        with pytest.raises(Refusal, match=re.escape(LOCAL_PROFILE.format(count=1))):
            refuse_local_profile(_prepared(kept, root=tmp_path), kept)


def test_the_region_hands_every_harness_the_pointer_and_the_essentials(tmp_path: Path) -> None:
    # Advisory output, so its mutation stays here: `lines = "\n".join(...)` -> `lines = ""` in
    # `_profile_block` reddens the loop.
    region = next(
        t
        for t in _prepared(_python(agents=("codex",)), root=tmp_path).footprint
        if t.id == "agents-md"
    ).render()
    assert "`docs/keelline/rules/python.md`" in region
    for line in load_profile("python").essentials:
        assert f"- {line}" in region
    # The block follows the paragraph after one blank line and adds none before the end marker.
    assert "\n\n\n" not in region and not region.endswith("\n\n")


def test_no_profile_means_no_profile_artifact_and_the_region_is_unchanged(
    tmp_path: Path,
) -> None:
    config = preset_defaults("widget")
    prepared = _prepared(config, root=tmp_path)
    assert not {t.id for t in prepared.footprint} & {"profile-rules", "claude-rules"}
    region = next(t for t in prepared.footprint if t.id == "agents-md").render()
    # Byte for byte what the region was before profiles: the shipped template with its
    # `%%PROFILE%%` sentinel taken out and every other sentinel filled. Mutation: make
    # `_profile_block` return `PROFILE_BLOCK` unfilled for no profile -> the equality reddens.
    p = config.paths
    before = fill(
        read("agents-region.md").replace("%%PROFILE%%", ""),
        BUG_INDEX=p.bug_index,
        BUGS=p.bugs,
        ROADMAP=p.roadmap,
        SPECS=p.specs,
        PLANS=p.plans,
    )
    assert region == before
    # That equality holds wherever the sentinel sits, so the position is its own assertion: the
    # sentinel ends the region's last line, and no blank line is left where it sat. Mutation:
    # put `%%PROFILE%%` on a line of its own -> this reddens.
    assert not region.endswith("\n\n")


def test_an_unknown_harness_name_is_counted_for_the_report(tmp_path: Path) -> None:
    prepared = _prepared(_python(agents=("claude", "cursor")), root=tmp_path)
    assert prepared.unknown_harnesses == 1


def test_a_rendition_that_collides_is_refused_naming_the_harness_s_fixed_name(
    tmp_path: Path,
) -> None:
    # A rendition's row is added where it is appended, not listed in `PATH_KEYS`, so this is the
    # case that proves the row exists: without it the collision is a `KeyError`, not a refusal.
    # Mutation (oracle): drop `keys[rendition.artifact_id] = OWN_NAME` -> reddens.
    config = _python(("claude",))
    clash = replace(config, paths=replace(config.paths, roadmap=".claude/rules/keelline-python.md"))
    with pytest.raises(Refusal, match=r"claude-rules \(a fixed name of Keelline's own\)"):
        _prepared(clash, root=tmp_path)
