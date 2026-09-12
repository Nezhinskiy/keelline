from __future__ import annotations

import json
import os
import stat
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from keelline.config.loader import CONFIG_FILE, load
from keelline.config.paths import PathEscape
from keelline.config.schema import Config
from keelline.errors import Refusal
from keelline.scaffold import engine
from keelline.scaffold.engine import apply, plan
from keelline.scaffold.entries import mark
from keelline.scaffold.manifest import Kind, Location, Manifest, Record, digest
from keelline.scaffold.model import Action, Plan, Template, Verb
from keelline.scaffold.regions import Style, upsert

CONFIG = """
[keelline]
version = "0.1.0"
state = "initialised"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"

[artifacts]
local = []
"""


def a_config(tmp_path: Path, *, local: tuple[str, ...] = ()) -> Config:
    text = CONFIG
    if local:
        text = text.replace("local = []", "local = [" + ", ".join(f'"{i}"' for i in local) + "]")
    (tmp_path / CONFIG_FILE).write_text(text, encoding="utf-8")
    return load(tmp_path, machine=tmp_path / "absent.toml")


def a_template(**overrides: object) -> Template:
    base = Template(
        id="agents-md",
        kind=Kind.TEMPLATE,
        target="AGENTS.md",
        source="project/AGENTS.md",
        render=lambda: "BODY\n",
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def a_record(**overrides: object) -> Record:
    values: dict[str, object] = {
        "id": "agents-md",
        "kind": Kind.TEMPLATE,
        "location": Location.REPO,
        "target": "AGENTS.md",
        "template": "project/AGENTS.md",
        "version": "0.1.0",
        "sha256": digest("BODY\n"),
    }
    values.update(overrides)
    return Record(**values)  # type: ignore[arg-type]


def a_settings_template(entries: dict[str, list[dict[str, Any]]]) -> Template:
    return a_template(
        id="claude-hooks",
        kind=Kind.KEYED_ENTRIES,
        target=".claude/settings.json",
        render=lambda: "",
        entries=entries,
    )


OURS: dict[str, list[dict[str, Any]]] = {
    "PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": mark("ours", "bg-cleanup")}]}
    ]
}


# --- whole files -------------------------------------------------------------------------


def test_an_unrecorded_absent_file_is_created(tmp_path: Path) -> None:
    result = plan(tmp_path, a_config(tmp_path), [a_template()])
    assert [(a.verb, a.target, a.payload) for a in result.actions] == [
        (Verb.CREATE, "AGENTS.md", "BODY\n")
    ]


def test_an_unrecorded_present_file_is_never_clobbered(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("someone wrote this\n", encoding="utf-8")
    result = plan(tmp_path, a_config(tmp_path), [a_template()])
    assert [a.verb for a in result.actions] == [Verb.SKIP_MODIFIED]


def test_a_recorded_unchanged_file_yields_no_action(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("BODY\n", encoding="utf-8")
    Manifest({}).with_record(a_record()).write(tmp_path)
    result = plan(tmp_path, a_config(tmp_path), [a_template()])
    assert result.actions == []
    assert result.unchanged == ["agents-md"]


def test_a_recorded_file_the_tool_wrote_is_updated(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("BODY\n", encoding="utf-8")
    Manifest({}).with_record(a_record()).write(tmp_path)
    result = plan(tmp_path, a_config(tmp_path), [a_template(render=lambda: "NEWER\n")])
    assert [(a.verb, a.payload) for a in result.actions] == [(Verb.UPDATE, "NEWER\n")]


def test_a_hand_edited_file_is_skipped_and_named(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("edited by hand\n", encoding="utf-8")
    Manifest({}).with_record(a_record()).write(tmp_path)
    result = plan(tmp_path, a_config(tmp_path), [a_template(render=lambda: "NEWER\n")])
    assert [(a.verb, a.target) for a in result.actions] == [(Verb.SKIP_MODIFIED, "AGENTS.md")]


def test_force_overrides_a_hand_edit(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("edited by hand\n", encoding="utf-8")
    Manifest({}).with_record(a_record()).write(tmp_path)
    result = plan(
        tmp_path, a_config(tmp_path), [a_template(render=lambda: "NEWER\n")], force=("AGENTS.md",)
    )
    assert [a.verb for a in result.actions] == [Verb.UPDATE]


def test_a_once_artifact_is_never_updated(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    template = a_template(id="claude-md", kind=Kind.ONCE, target="CLAUDE.md")
    result = plan(tmp_path, a_config(tmp_path), [template])
    assert result.actions == []
    assert result.unchanged == ["claude-md"]


def test_a_retired_template_is_removed_while_its_hash_matches(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("BODY\n", encoding="utf-8")
    Manifest({}).with_record(a_record()).write(tmp_path)
    result = plan(tmp_path, a_config(tmp_path), [a_template(retired=True)])
    assert [(a.verb, a.target, a.payload) for a in result.actions] == [
        (Verb.REMOVE, "AGENTS.md", None)
    ]


def test_a_retired_template_edited_by_hand_is_reported_not_removed(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("mine now\n", encoding="utf-8")
    Manifest({}).with_record(a_record()).write(tmp_path)
    result = plan(tmp_path, a_config(tmp_path), [a_template(retired=True)])
    assert [a.verb for a in result.actions] == [Verb.SKIP_MODIFIED]


def test_a_local_artifact_moves_under_dot_keelline(tmp_path: Path) -> None:
    config = a_config(tmp_path, local=("agents-md",))
    result = plan(tmp_path, config, [a_template()])
    assert [a.target for a in result.actions] == [".keelline/local/AGENTS.md"]


def test_a_relocated_artifact_is_removed_from_its_old_home(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("BODY\n", encoding="utf-8")
    Manifest({}).with_record(a_record()).write(tmp_path)
    config = a_config(tmp_path, local=("agents-md",))
    result = plan(tmp_path, config, [a_template()])
    assert [(a.verb, a.target) for a in result.actions] == [
        (Verb.REMOVE, "AGENTS.md"),
        (Verb.CREATE, ".keelline/local/AGENTS.md"),
    ]


def test_a_manifest_naming_a_target_outside_the_root_plans_nothing_for_it(tmp_path: Path) -> None:
    # The manifest is committed, so `record.target` is repository-controlled input.
    root = tmp_path / "project"
    root.mkdir()
    (tmp_path / "outside.md").write_text("BODY\n", encoding="utf-8")
    Manifest({}).with_record(a_record(target="../outside.md")).write(root)
    config = a_config(root, local=("agents-md",))
    result = plan(root, config, [a_template()])
    assert [a.verb for a in result.actions] == [Verb.CREATE]
    assert (tmp_path / "outside.md").exists()


# --- regions and keyed entries, which live inside somebody else's file ---------------------


def test_a_managed_region_is_installed_into_a_file_no_record_covers(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("PROSE\n", encoding="utf-8")
    template = a_template(kind=Kind.MANAGED_REGION, region="harness", render=lambda: "R1")
    first = plan(tmp_path, a_config(tmp_path), [template])
    assert first.actions[0].verb is Verb.REGION_UPDATE
    assert first.actions[0].payload is not None
    assert first.actions[0].payload.startswith("PROSE\n")
    assert "R1" in first.actions[0].payload


def test_a_region_already_current_yields_no_action(tmp_path: Path) -> None:
    text = upsert("PROSE\n", "harness", "R1", Style.MARKDOWN)
    (tmp_path / "AGENTS.md").write_text(text, encoding="utf-8")
    Manifest({}).with_record(a_record(kind=Kind.MANAGED_REGION, sha256=digest("R1"))).write(
        tmp_path
    )
    template = a_template(kind=Kind.MANAGED_REGION, region="harness", render=lambda: "R1")
    assert plan(tmp_path, a_config(tmp_path), [template]).actions == []


def test_prose_around_a_region_may_change_without_reading_as_a_hand_edit(tmp_path: Path) -> None:
    text = upsert("PROSE\n", "harness", "R1", Style.MARKDOWN) + "a paragraph the user added\n"
    (tmp_path / "AGENTS.md").write_text(text, encoding="utf-8")
    Manifest({}).with_record(a_record(kind=Kind.MANAGED_REGION, sha256=digest("R1"))).write(
        tmp_path
    )
    template = a_template(kind=Kind.MANAGED_REGION, region="harness", render=lambda: "R2")
    assert [a.verb for a in plan(tmp_path, a_config(tmp_path), [template]).actions] == [
        Verb.REGION_UPDATE
    ]


def test_a_hand_edited_region_body_is_skipped(tmp_path: Path) -> None:
    text = upsert("PROSE\n", "harness", "EDITED BY HAND", Style.MARKDOWN)
    (tmp_path / "AGENTS.md").write_text(text, encoding="utf-8")
    Manifest({}).with_record(a_record(kind=Kind.MANAGED_REGION, sha256=digest("R1"))).write(
        tmp_path
    )
    template = a_template(kind=Kind.MANAGED_REGION, region="harness", render=lambda: "R2")
    assert [a.verb for a in plan(tmp_path, a_config(tmp_path), [template]).actions] == [
        Verb.SKIP_MODIFIED
    ]


def test_a_retired_region_leaves_the_file_and_removes_only_its_own_lines(tmp_path: Path) -> None:
    text = upsert("PROSE\n", "harness", "R1", Style.MARKDOWN)
    (tmp_path / "AGENTS.md").write_text(text, encoding="utf-8")
    Manifest({}).with_record(a_record(kind=Kind.MANAGED_REGION, sha256=digest("R1"))).write(
        tmp_path
    )
    template = a_template(
        kind=Kind.MANAGED_REGION, region="harness", render=lambda: "R1", retired=True
    )
    planned = plan(tmp_path, a_config(tmp_path), [template])
    assert [a.verb for a in planned.actions] == [Verb.REMOVE]
    apply(tmp_path, planned)
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "PROSE\n"


def test_keyed_entries_are_installed_into_a_file_no_record_covers(tmp_path: Path) -> None:
    settings = tmp_path / ".claude"
    settings.mkdir()
    (settings / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "Bash", "hooks": [{"type": "command", "command": "theirs"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    result = plan(tmp_path, a_config(tmp_path), [a_settings_template(OURS)])
    assert result.actions[0].verb is Verb.ENTRIES_UPDATE
    assert result.actions[0].payload is not None
    assert "theirs" in result.actions[0].payload


def test_an_unrelated_edit_beside_the_entries_is_not_a_hand_edit(tmp_path: Path) -> None:
    template = a_settings_template(OURS)
    first = plan(tmp_path, a_config(tmp_path), [template])
    apply(tmp_path, first)
    settings = tmp_path / ".claude" / "settings.json"
    raw = json.loads(settings.read_text(encoding="utf-8"))
    raw["permissions"] = {"deny": ["Read(./.env)"]}
    settings.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    again = plan(tmp_path, a_config(tmp_path), [template])
    assert again.actions == []
    assert again.unchanged == ["claude-hooks"]


def test_a_retired_keyed_entry_leaves_the_rest_of_the_document(tmp_path: Path) -> None:
    template = a_settings_template(OURS)
    apply(tmp_path, plan(tmp_path, a_config(tmp_path), [template]))
    planned = plan(tmp_path, a_config(tmp_path), [replace(template, retired=True)])
    assert [a.verb for a in planned.actions] == [Verb.REMOVE]
    apply(tmp_path, planned)
    text = (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    assert "keelline:bg-cleanup" not in text
    assert (tmp_path / ".claude" / "settings.json").exists()


# --- refusals ------------------------------------------------------------------------------


@pytest.mark.parametrize("target", ["../outside.md", "/etc/keelline.md", "docs/../../x.md", ""])
def test_an_escaping_target_is_refused_not_planned(tmp_path: Path, target: str) -> None:
    result = plan(tmp_path, a_config(tmp_path), [a_template(target=target)])
    assert result.actions == []
    assert [r.artifact_id for r in result.refusals] == ["agents-md"]


def test_one_refused_template_does_not_hide_the_others(tmp_path: Path) -> None:
    result = plan(
        tmp_path,
        a_config(tmp_path),
        [a_template(id="bad", target="../x"), a_template(id="good", target="GOOD.md")],
    )
    assert [a.artifact_id for a in result.actions] == ["good"]
    assert [r.artifact_id for r in result.refusals] == ["bad"]


def test_an_unreadable_file_refuses_only_its_own_artifact(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_bytes(b"\xff\xfe not utf-8 \xff")
    result = plan(
        tmp_path,
        a_config(tmp_path),
        [a_template(), a_template(id="good", target="GOOD.md")],
    )
    assert [a.artifact_id for a in result.actions] == ["good"]
    assert [r.artifact_id for r in result.refusals] == ["agents-md"]


@pytest.mark.parametrize("profile", ["../../etc/passwd", "/etc", "..", "Python", "no such"])
def test_a_malformed_profile_is_refused(tmp_path: Path, profile: str) -> None:
    text = CONFIG.replace('profile = ""', f'profile = "{profile}"')
    (tmp_path / CONFIG_FILE).write_text(text, encoding="utf-8")
    config = load(tmp_path, machine=tmp_path / "absent.toml")
    with pytest.raises(PathEscape, match="profile"):
        plan(tmp_path, config, [a_template()])


def test_a_well_formed_profile_is_allowed_while_no_listing_exists(tmp_path: Path) -> None:
    # Until the `profile-python` lane creates `profiles/`, there is nothing to check a name
    # against, and refusing every name would make `init --yes` produce a config plan() rejects.
    text = CONFIG.replace('profile = ""', 'profile = "python"')
    (tmp_path / CONFIG_FILE).write_text(text, encoding="utf-8")
    config = load(tmp_path, machine=tmp_path / "absent.toml")
    assert plan(tmp_path, config, [a_template()]).actions != []


def test_an_empty_profile_means_none_and_is_allowed(tmp_path: Path) -> None:
    assert plan(tmp_path, a_config(tmp_path), [a_template()]).actions != []


# --- apply ----------------------------------------------------------------------------------


def test_apply_writes_the_payload_and_records_it(tmp_path: Path) -> None:
    config = a_config(tmp_path)
    result = apply(tmp_path, plan(tmp_path, config, [a_template()]))
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "BODY\n"
    assert result.written == ["AGENTS.md"]
    assert Manifest.read(tmp_path).get("agents-md") is not None


def test_apply_refuses_a_plan_carrying_a_refusal(tmp_path: Path) -> None:
    config = a_config(tmp_path)
    planned = plan(tmp_path, config, [a_template(target="../outside.md")])
    with pytest.raises(Refusal, match="refused"):
        apply(tmp_path, planned)


def test_a_symlink_planted_between_plan_and_apply_is_refused(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    config = a_config(tmp_path)
    (tmp_path / "docs").mkdir()
    planned = plan(tmp_path, config, [a_template(target="docs/AGENTS.md")])
    (tmp_path / "docs").rmdir()
    (tmp_path / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(Refusal):
        apply(tmp_path, planned)
    assert list(outside.iterdir()) == []


def test_apply_refuses_a_dotdot_target_no_symlink_walk_would_catch(tmp_path: Path) -> None:
    # The plan is built by hand because `plan()` would refuse this target and `apply()` would
    # then stop on the refusal instead of on the guard under test. `..` is an ordinary
    # directory entry, so `open_within`'s O_NOFOLLOW walk opens it without objecting: the
    # `contained()` call `apply` makes at write time is the only thing between this action and
    # a write outside the root.
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    action = Action(Verb.CREATE, "agents-md", f"../{outside.name}/AGENTS.md", "BODY\n", "new", None)
    with pytest.raises(PathEscape, match=r"\.\."):
        apply(tmp_path, Plan(actions=[action]))
    assert list(outside.iterdir()) == []


def test_the_write_refuses_a_symlinked_parent_containment_never_saw(tmp_path: Path) -> None:
    # The writer is called directly, with no `contained()` ahead of it, because that is the
    # shape of the race this layer exists to close: the check has already passed by the time a
    # component becomes a symlink. The empty `deep/` directory the refused write leaves outside
    # the root is a known defect of the foundation writer, raised separately; what this test
    # pins is that no content follows the link.
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(Refusal):
        engine._write(tmp_path, "docs/deep/AGENTS.md", "BODY\n")
    assert [path for path in outside.rglob("*") if path.is_file()] == []


def test_a_removal_deletes_the_file_and_the_record(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("BODY\n", encoding="utf-8")
    Manifest({}).with_record(a_record()).write(tmp_path)
    config = a_config(tmp_path)
    result = apply(tmp_path, plan(tmp_path, config, [a_template(retired=True)]))
    assert not (tmp_path / "AGENTS.md").exists()
    assert result.removed == ["AGENTS.md"]
    assert Manifest.read(tmp_path).get("agents-md") is None


def test_a_local_artifact_is_written_but_never_recorded(tmp_path: Path) -> None:
    config = a_config(tmp_path, local=("agents-md",))
    apply(tmp_path, plan(tmp_path, config, [a_template()]))
    assert (tmp_path / ".keelline/local/AGENTS.md").read_text(encoding="utf-8") == "BODY\n"
    assert Manifest.read(tmp_path).records == {}


def test_a_skipped_artifact_is_reported_and_not_written(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("mine\n", encoding="utf-8")
    config = a_config(tmp_path)
    result = apply(tmp_path, plan(tmp_path, config, [a_template()]))
    assert result.skipped == ["AGENTS.md"]
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "mine\n"


def test_no_temporary_file_survives_a_write(tmp_path: Path) -> None:
    config = a_config(tmp_path)
    apply(tmp_path, plan(tmp_path, config, [a_template()]))
    assert sorted(p.name for p in tmp_path.iterdir()) == [".keelline", "AGENTS.md", CONFIG_FILE]


def test_an_updated_file_keeps_the_mode_it_had(tmp_path: Path) -> None:
    config = a_config(tmp_path)
    apply(tmp_path, plan(tmp_path, config, [a_template()]))
    os.chmod(tmp_path / "AGENTS.md", 0o664)
    apply(tmp_path, plan(tmp_path, config, [a_template(render=lambda: "NEWER\n")]))
    assert stat.S_IMODE((tmp_path / "AGENTS.md").stat().st_mode) == 0o664


def test_a_created_file_is_readable_by_more_than_its_owner(tmp_path: Path) -> None:
    config = a_config(tmp_path)
    apply(tmp_path, plan(tmp_path, config, [a_template()]))
    assert stat.S_IMODE((tmp_path / "AGENTS.md").stat().st_mode) == 0o644
