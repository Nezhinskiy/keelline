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
from keelline.scaffold.manifest import (
    MANIFEST_PATH,
    Kind,
    Location,
    Manifest,
    Record,
    digest,
)
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
    assert result.actions == ()
    assert result.unchanged == ("agents-md",)


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
    # `skip_modified` and not `unchanged`: the plan's decision table says so, and `unchanged`
    # renders as "up to date" for a file Keelline deliberately never looks inside again. The
    # user needs "left alone because it is yours", which is the statement that is true.
    (tmp_path / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    template = a_template(id="claude-md", kind=Kind.ONCE, target="CLAUDE.md")
    result = plan(tmp_path, a_config(tmp_path), [template])
    assert [(a.verb, a.target) for a in result.actions] == [(Verb.SKIP_MODIFIED, "CLAUDE.md")]
    assert result.unchanged == ()
    before = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert apply(tmp_path, result).skipped == ("CLAUDE.md",)
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == before


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


def test_a_relocated_artifact_whose_old_file_was_hand_edited_is_reported(tmp_path: Path) -> None:
    # The plan was `[(create, .keelline/local/AGENTS.md)]`, the report said "0 skipped, 0
    # refused", the old file stayed on disk holding the user's edit, and the manifest ended
    # empty — which `apply`'s own comment calls a defect: "a file Keelline wrote carrying no
    # record, which every later run reads as somebody else's … invisible to `uninstall`". The
    # symmetric `_plan_retired` path has always emitted `skip_modified` for this.
    old = tmp_path / "AGENTS.md"
    old.write_text("BODY\nand a line the user added\n", encoding="utf-8")
    Manifest({}).with_record(a_record()).write(tmp_path)  # recorded sha256 is of "BODY\n"
    config = a_config(tmp_path, local=("agents-md",))
    result = plan(tmp_path, config, [a_template()])
    assert [(a.verb, a.target) for a in result.actions] == [
        (Verb.SKIP_MODIFIED, "AGENTS.md"),
        (Verb.CREATE, ".keelline/local/AGENTS.md"),
    ]
    assert result.actions[0].reason == "relocated and hand-edited"
    applied = apply(tmp_path, result)
    assert applied.skipped == ("AGENTS.md",)
    assert old.read_text(encoding="utf-8") == "BODY\nand a line the user added\n"


def test_a_relocation_whose_old_file_is_already_gone_reports_no_skip(tmp_path: Path) -> None:
    # The one branch that must stay silent: nothing at the old path means the move has already
    # happened, and a `skip_modified` there would report a file that is not on disk.
    Manifest({}).with_record(a_record()).write(tmp_path)
    config = a_config(tmp_path, local=("agents-md",))
    result = plan(tmp_path, config, [a_template()])
    assert [(a.verb, a.target) for a in result.actions] == [
        (Verb.REMOVE, "AGENTS.md"),
        (Verb.CREATE, ".keelline/local/AGENTS.md"),
    ]
    assert apply(tmp_path, result).skipped == ()


def test_a_manifest_naming_a_target_outside_the_root_plans_nothing_for_it(tmp_path: Path) -> None:
    # The manifest is committed, so `record.target` is repository-controlled input.
    root = tmp_path / "project"
    root.mkdir()
    (tmp_path / "outside.md").write_text("BODY\n", encoding="utf-8")
    Manifest({}).with_record(a_record(target="../outside.md")).write(root)
    config = a_config(root, local=("agents-md",))
    result = plan(root, config, [a_template()])
    # Said out loud, not silent. The file is still not touched — that is the property — but a
    # record naming a file Keelline will not remove is something the report has to carry, or
    # the artifact is created at its new target with the old one left on disk and nothing said.
    assert [a.verb for a in result.actions] == [Verb.SKIP_MODIFIED, Verb.CREATE]
    assert result.actions[0].target == "../outside.md"
    assert (tmp_path / "outside.md").exists()


def test_a_recorded_target_this_template_could_never_produce_is_not_a_relocation(
    tmp_path: Path,
) -> None:
    # Both halves of "is this file ours" come out of the committed manifest: the recorded target
    # and the recorded hash. So without a guard, naming any file in the root and stamping it with
    # the bytes it is committed with is enough to make `plan` emit a REMOVE for it — and a
    # mismatch between the recorded target and the effective one is all it takes, with no
    # `[artifacts] local` entry and so no relocation anywhere in sight.
    victim = tmp_path / ".claude"
    victim.mkdir()
    settings = victim / "settings.json"
    before = '{"permissions": {"deny": ["Read(./.env)"]}}\n'
    settings.write_text(before, encoding="utf-8")
    record = a_record(target=".claude/settings.json", sha256=digest(before))
    Manifest({}).with_record(record).write(tmp_path)
    planned = plan(tmp_path, a_config(tmp_path), [a_template()])
    assert [(a.verb, a.target) for a in planned.actions] == [
        (Verb.SKIP_MODIFIED, ".claude/settings.json"),
        (Verb.CREATE, "AGENTS.md"),
    ]
    applied = apply(tmp_path, planned)
    assert settings.read_text(encoding="utf-8") == before
    assert applied.skipped == (".claude/settings.json",)


def test_relocating_a_managed_region_removes_only_its_own_lines(tmp_path: Path) -> None:
    # A relocation's REMOVE goes through the same writer as a retirement's, so it needs the same
    # payload. For a region the file at the old path is the user's own; unlinking it takes their
    # prose with it, while `_plan_retired` in the same module strips just the marked block.
    host = tmp_path / "AGENTS.md"
    body = upsert("User prose.\n", "harness", "R1\n", Style.MARKDOWN)
    host.write_text(body, encoding="utf-8")
    Manifest({}).with_record(a_record(kind=Kind.MANAGED_REGION, sha256=digest(body))).write(
        tmp_path
    )
    config = a_config(tmp_path, local=("agents-md",))
    template = a_template(kind=Kind.MANAGED_REGION, region="harness", render=lambda: "R1\n")
    planned = plan(tmp_path, config, [template])
    assert [(a.verb, a.target) for a in planned.actions] == [
        (Verb.REMOVE, "AGENTS.md"),
        (Verb.CREATE, ".keelline/local/AGENTS.md"),
    ]
    apply(tmp_path, planned)
    assert host.read_text(encoding="utf-8") == "User prose.\n"


def test_a_local_artifact_is_refreshed_rather_than_read_as_somebody_elses(tmp_path: Path) -> None:
    # A local artifact is deliberately never recorded, so `record is None` holds for it on every
    # run after the first. `.keelline/local/` is Keelline's own directory, so that says nothing
    # about who wrote the file — and reading it as "somebody's" made every local artifact
    # create-once, under a reason that is false and ahead of the point where `force` is consulted.
    config = a_config(tmp_path, local=("agents-md",))
    local = tmp_path / ".keelline" / "local" / "AGENTS.md"
    apply(tmp_path, plan(tmp_path, config, [a_template()]))
    assert local.read_text(encoding="utf-8") == "BODY\n"
    planned = plan(tmp_path, config, [a_template(render=lambda: "NEWER\n")])
    assert [(a.verb, a.reason) for a in planned.actions] == [(Verb.UPDATE, "refreshed")]
    apply(tmp_path, planned)
    assert local.read_text(encoding="utf-8") == "NEWER\n"
    assert Manifest.read(tmp_path).records == {}


def test_a_local_artifact_whose_content_already_matches_is_unchanged(tmp_path: Path) -> None:
    # The other half: refreshing unconditionally would rewrite a file nothing changed in on
    # every run, which is the report saying work happened when none did.
    config = a_config(tmp_path, local=("agents-md",))
    apply(tmp_path, plan(tmp_path, config, [a_template()]))
    again = plan(tmp_path, config, [a_template()])
    assert again.actions == ()
    assert again.unchanged == ("agents-md",)


def test_a_retired_local_artifact_is_removed(tmp_path: Path) -> None:
    # `uninstall` has to be able to finish. A retirement is decided against the record for a
    # repository file, and a local artifact has none by design — so for this one directory the
    # question is answered without one rather than answered "leave it".
    config = a_config(tmp_path, local=("agents-md",))
    local = tmp_path / ".keelline" / "local" / "AGENTS.md"
    apply(tmp_path, plan(tmp_path, config, [a_template()]))
    planned = plan(tmp_path, config, [a_template(retired=True)])
    assert [(a.verb, a.target) for a in planned.actions] == [
        (Verb.REMOVE, ".keelline/local/AGENTS.md")
    ]
    apply(tmp_path, planned)
    assert not local.exists()


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
    assert plan(tmp_path, a_config(tmp_path), [template]).actions == ()


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
    assert again.actions == ()
    assert again.unchanged == ("claude-hooks",)


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
    assert result.actions == ()
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


def test_a_doubled_region_marker_refuses_only_its_own_artifact(tmp_path: Path) -> None:
    # A bad merge, not an internal bug. §7.2 answers it with a refusal for this one artifact,
    # and `render_report`'s REFUSED section exists to name exactly these — which it can only do
    # if a plan is returned at all.
    (tmp_path / "AGENTS.md").write_text(
        "PROSE\n"
        "<!-- keelline:harness:begin -->\nfirst\n<!-- keelline:harness:end -->\n"
        "<!-- keelline:harness:begin -->\nsecond\n<!-- keelline:harness:end -->\n",
        encoding="utf-8",
    )
    result = plan(
        tmp_path,
        a_config(tmp_path),
        [
            a_template(kind=Kind.MANAGED_REGION, region="harness", render=lambda: "R1"),
            a_template(id="good", target="GOOD.md"),
        ],
    )
    assert [(r.artifact_id, "twice" in r.reason) for r in result.refusals] == [("agents-md", True)]
    assert [(a.artifact_id, a.verb) for a in result.actions] == [("good", Verb.CREATE)]


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ("{not json", "not valid JSON"),
        ('{"hooks": "not an object"}', "'hooks' is not an object"),
    ],
)
def test_a_settings_document_the_engine_cannot_parse_refuses_only_its_own_artifact(
    tmp_path: Path, document: str, expected: str
) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(document, encoding="utf-8")
    result = plan(
        tmp_path,
        a_config(tmp_path),
        [a_settings_template(OURS), a_template(id="good", target="GOOD.md")],
    )
    assert [(r.artifact_id, expected in r.reason) for r in result.refusals] == [
        ("claude-hooks", True)
    ]
    assert [(a.artifact_id, a.verb) for a in result.actions] == [("good", Verb.CREATE)]


def test_a_keyed_entries_template_naming_no_entries_raises(tmp_path: Path) -> None:
    # The symmetric case, and the one that was missing. `Template.entries` defaults to `None`
    # and `apply_entries(current, {})` means "remove every Keelline entry", so a lane that
    # forgot one keyword argument uninstalled the user's hook wiring — reported as
    # `entries_update` / "refreshed", with the manifest rewritten as an ordinary upgrade.
    settings = tmp_path / ".claude"
    settings.mkdir()
    (settings / "settings.json").write_text(json.dumps({"hooks": OURS}), encoding="utf-8")
    template = a_settings_template(OURS)
    with pytest.raises(Refusal, match="names no entries"):
        plan(tmp_path, a_config(tmp_path), [replace(template, entries=None)])


def test_a_keyed_entries_template_whose_entries_carry_no_marker_raises(tmp_path: Path) -> None:
    # The third face of the same defect, and the one that was silent in the *install*
    # direction. `_payload_and_stamp` stamps `owned(document)` — the marked entries alone — so
    # with none of them marked `owned()` answers `{}` for the payload and `{}` for what is
    # already on disk, the digests match, and `plan` reports the artifact `unchanged`. Measured
    # before the fix, against a template whose command is `keelline hook PreToolUse` and no
    # `mark()`: actions `[]`, unchanged `('hooks',)`, `apply` wrote nothing, and the user's
    # `.claude/settings.json` still had no hook wiring in it while the report said up to date.
    settings = tmp_path / ".claude"
    settings.mkdir()
    (settings / "settings.json").write_text(json.dumps({"hooks": OURS}), encoding="utf-8")
    unmarked_entries: dict[str, list[dict[str, Any]]] = {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": "keelline hook PreToolUse"}],
            }
        ]
    }
    with pytest.raises(Refusal, match="no `# keelline:<id>` marker"):
        plan(tmp_path, a_config(tmp_path), [a_settings_template(unmarked_entries)])


def test_one_unmarked_entry_beside_a_marked_one_is_still_a_refusal(tmp_path: Path) -> None:
    # Not "no entry is marked" — *any* unmarked entry is one this module's own two rules say
    # belongs to somebody else, so it would be installed once and then left alone for ever,
    # while `owned()` stamps only its marked neighbour. A check on the whole mapping rather
    # than on it being empty is what tells those apart.
    settings = tmp_path / ".claude"
    settings.mkdir()
    (settings / "settings.json").write_text(json.dumps({"hooks": OURS}), encoding="utf-8")
    mixed: dict[str, list[dict[str, Any]]] = {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {"type": "command", "command": mark("ours", "bg-cleanup")},
                    {"type": "command", "command": "keelline hook PreToolUse"},
                ],
            }
        ]
    }
    with pytest.raises(Refusal, match="'keelline hook PreToolUse'"):
        plan(tmp_path, a_config(tmp_path), [a_settings_template(mixed)])


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param({"type": "command", "command": ["ls"]}, id="command-is-not-a-string"),
        pytest.param({"type": "command"}, id="no-command-at-all"),
        pytest.param("keelline hook PreToolUse", id="entry-is-not-an-object"),
    ],
)
def test_an_entry_that_cannot_be_keyed_is_refused_rather_than_written(
    tmp_path: Path, entry: object
) -> None:
    # `apply_entries` writes `wanted` into the user's file verbatim, and nothing between a lane
    # and that write validates its shape — `_entries_of` checks the *document*, not the mapping
    # coming in. An entry that cannot be keyed is the same bug whatever makes it unkeyable, and
    # the last case is why the shape guard is a guard rather than decoration: without it
    # `entry.get` raises `AttributeError` out of `plan` instead of naming the lane's bug.
    settings = tmp_path / ".claude"
    settings.mkdir()
    (settings / "settings.json").write_text(json.dumps({"hooks": OURS}), encoding="utf-8")
    malformed: dict[str, list[dict[str, Any]]] = {
        "PreToolUse": [{"matcher": "Bash", "hooks": [entry]}]
    }
    with pytest.raises(Refusal, match="no `# keelline:<id>` marker"):
        plan(tmp_path, a_config(tmp_path), [a_settings_template(malformed)])


def test_an_empty_entries_mapping_still_means_remove_everything(tmp_path: Path) -> None:
    # `{}` is left meaning exactly what it meant: the caller that genuinely wants every marked
    # entry gone. Only `None` — the default nobody chose — became a refusal.
    settings = tmp_path / ".claude"
    settings.mkdir()
    (settings / "settings.json").write_text(json.dumps({"hooks": OURS}), encoding="utf-8")
    result = plan(tmp_path, a_config(tmp_path), [a_settings_template({})])
    assert [a.verb for a in result.actions] == [Verb.ENTRIES_UPDATE]
    apply(tmp_path, result)
    assert json.loads((settings / "settings.json").read_text(encoding="utf-8")) == {}


def test_a_template_naming_no_region_raises_rather_than_becoming_a_refusal(tmp_path: Path) -> None:
    # The boundary of what `plan` converts into a per-artifact refusal. A `MANAGED_REGION`
    # template carrying no region name is a malformed `Template`, so it is a bug in the lane
    # that built it; recording it beside the user's own bad merges would hide it.
    template = a_template(kind=Kind.MANAGED_REGION, region=None, render=lambda: "R1")
    (tmp_path / "AGENTS.md").write_text("PROSE\n", encoding="utf-8")
    with pytest.raises(Refusal, match="names no region"):
        plan(tmp_path, a_config(tmp_path), [template])


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
    assert plan(tmp_path, config, [a_template()]).actions != ()


def test_an_empty_profile_means_none_and_is_allowed(tmp_path: Path) -> None:
    assert plan(tmp_path, a_config(tmp_path), [a_template()]).actions != ()


def test_a_file_carrying_only_a_region_end_marker_is_refused_and_left_alone(
    tmp_path: Path,
) -> None:
    # A begin line somebody deleted, or a merge that kept one side's end marker. Read as "region
    # absent", the first run appended a fresh block and wrote a second end marker itself, and
    # every run after that refused a file Keelline had broken — `uninstall` included.
    before = "Prose.\n<!-- keelline:harness:end -->\n"
    (tmp_path / "AGENTS.md").write_text(before, encoding="utf-8")
    template = a_template(kind=Kind.MANAGED_REGION, region="harness", render=lambda: "R1")
    first = plan(tmp_path, a_config(tmp_path), [template])
    assert first.actions == ()
    assert [(r.artifact_id, "no beginning" in r.reason) for r in first.refusals] == [
        ("agents-md", True)
    ]
    with pytest.raises(Refusal):
        apply(tmp_path, first)
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == before


def test_a_profile_name_with_a_trailing_newline_is_refused(tmp_path: Path) -> None:
    # `$` matches before a final newline as well as at the end of the string, so the one-segment
    # check accepted a name carrying a line break. `shipped_profiles()` returns None while no
    # listing exists, which makes this regex the only guard on the field.
    text = CONFIG.replace('profile = ""', 'profile = "python\\n"')
    (tmp_path / CONFIG_FILE).write_text(text, encoding="utf-8")
    config = load(tmp_path, machine=tmp_path / "absent.toml")
    assert config.keelline.profile == "python\n"
    with pytest.raises(PathEscape, match="profile"):
        plan(tmp_path, config, [a_template()])


# --- apply ----------------------------------------------------------------------------------


def test_apply_writes_the_payload_and_records_it(tmp_path: Path) -> None:
    config = a_config(tmp_path)
    result = apply(tmp_path, plan(tmp_path, config, [a_template()]))
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "BODY\n"
    assert result.written == ("AGENTS.md",)
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
        apply(tmp_path, Plan(actions=(action,)))
    assert list(outside.iterdir()) == []


def test_the_write_refuses_a_symlinked_parent_containment_never_saw(tmp_path: Path) -> None:
    # The writer is called directly, with no `contained()` ahead of it, because that is the
    # shape of the race this layer exists to close: the check has already passed by the time a
    # component becomes a symlink. Nothing at all follows the link — not the content, and not
    # the parent directories, because `_mkdirs_within` creates those through the same
    # O_NOFOLLOW walk instead of handing the string to `Path.mkdir`.
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(Refusal):
        engine._write(tmp_path, "docs/deep/AGENTS.md", "BODY\n")
    assert list(outside.iterdir()) == []


def test_a_removal_deletes_the_file_and_the_record(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("BODY\n", encoding="utf-8")
    Manifest({}).with_record(a_record()).write(tmp_path)
    config = a_config(tmp_path)
    result = apply(tmp_path, plan(tmp_path, config, [a_template(retired=True)]))
    assert not (tmp_path / "AGENTS.md").exists()
    assert result.removed == ("AGENTS.md",)
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
    assert result.skipped == ("AGENTS.md",)
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


def test_a_committed_symlink_at_dot_keelline_refuses_before_anything_is_written(
    tmp_path: Path,
) -> None:
    # git stores symlinks, so a clone materialises this one, and no race is needed: without a
    # containment check the manifest — records and all — is written wherever the link points.
    root = tmp_path / "project"
    root.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (root / ".keelline").symlink_to(victim, target_is_directory=True)
    config = a_config(root)
    with pytest.raises(PathEscape, match="symlink"):
        plan(root, config, [a_template()])
    assert list(victim.iterdir()) == []
    assert not (root / "AGENTS.md").exists()


def test_dot_keelline_symlinked_after_the_plan_makes_apply_refuse(tmp_path: Path) -> None:
    # The same escape in the race shape the dry run cannot see: the plan was clean when the
    # user read it. `apply` must refuse with nothing written, inside the root or outside it.
    root = tmp_path / "project"
    root.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    config = a_config(root)
    planned = plan(root, config, [a_template()])
    (root / ".keelline").symlink_to(victim, target_is_directory=True)
    with pytest.raises(PathEscape, match="symlink"):
        apply(root, planned)
    assert list(victim.iterdir()) == []
    assert not (root / "AGENTS.md").exists()


def test_a_file_where_a_directory_belongs_refuses_rather_than_raising_oserror(
    tmp_path: Path,
) -> None:
    # No race and no symlink: the user saves a file at `docs` while reading the dry-run report,
    # then confirms. A bare `OSError` here reaches the CLI as a traceback instead of C5's
    # exit 2, which is what a refusal is for.
    config = a_config(tmp_path)
    planned = plan(tmp_path, config, [a_template(id="doc", target="docs/README.md")])
    (tmp_path / "docs").write_text("a file the user just saved\n", encoding="utf-8")
    with pytest.raises(Refusal):
        apply(tmp_path, planned)
    assert (tmp_path / "docs").read_text(encoding="utf-8") == "a file the user just saved\n"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the directory mode under test")
def test_a_directory_that_cannot_be_created_refuses_rather_than_raising_oserror(
    tmp_path: Path,
) -> None:
    # The other half of "no bare OSError": a parent directory Keelline may read but not write
    # to. `open_within` opens it happily — r-x is enough — so this arrives as EACCES from
    # `os.mkdir` rather than as an `UnsafePath`, and only the broad clause turns it into exit 2.
    (tmp_path / "docs").mkdir()
    os.chmod(tmp_path / "docs", stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(Refusal, match="cannot be written"):
            engine._write(tmp_path, "docs/specs/README.md", "S\n")
    finally:
        os.chmod(tmp_path / "docs", 0o755)
    assert not (tmp_path / "docs" / "specs").exists()


def test_crlf_endings_outside_a_managed_region_survive_plan_and_apply(tmp_path: Path) -> None:
    # `regions.py` promises to return every byte outside its own markers unchanged, and
    # `test_regions.py` proves it by calling `upsert` directly. This measures the same property
    # where a user meets it: a universal-newline read rewrites every ending in the file before
    # `upsert` is ever reached, so the promise is kept or broken here, not there.
    before = b"# Title\r\n\r\nProse the tool must never touch.\r\n"
    (tmp_path / "AGENTS.md").write_bytes(before)
    template = a_template(kind=Kind.MANAGED_REGION, region="harness", render=lambda: "R1")
    apply(tmp_path, plan(tmp_path, a_config(tmp_path), [template]))
    assert (tmp_path / "AGENTS.md").read_bytes() == before + (
        b"<!-- keelline:harness:begin -->\r\nR1\r\n<!-- keelline:harness:end -->\r\n"
    )


def test_reordering_the_keys_inside_a_marked_entry_is_not_a_hand_edit(tmp_path: Path) -> None:
    # `owned()`'s canonical rendering is the only thing making this true. Without it, a user who
    # writes "command" before "type" inside Keelline's own hook entry has changed no value and
    # still flips the artifact to `skip_modified` for good.
    template = a_settings_template(OURS)
    apply(tmp_path, plan(tmp_path, a_config(tmp_path), [template]))
    settings = tmp_path / ".claude" / "settings.json"
    raw = json.loads(settings.read_text(encoding="utf-8"))
    entry = raw["hooks"]["PreToolUse"][0]["hooks"][0]
    reordered = dict(reversed(list(entry.items())))
    assert list(reordered) != list(entry)
    raw["hooks"]["PreToolUse"][0]["hooks"][0] = reordered
    settings.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    again = plan(tmp_path, a_config(tmp_path), [template])
    assert [(a.verb, a.reason) for a in again.actions] == []
    assert again.unchanged == ("claude-hooks",)


def test_apply_records_the_files_it_wrote_before_a_later_action_refused(tmp_path: Path) -> None:
    # The ledger describes the disk, so it cannot be discarded for actions that already ran. A
    # file Keelline wrote and did not record reads as somebody else's on every later run:
    # `skip_modified` under a reason that is false, proof against `--force` because the absent
    # record is consulted first, and invisible to `uninstall`.
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    config = a_config(tmp_path)
    (tmp_path / "docs").mkdir()
    planned = plan(
        tmp_path,
        config,
        [
            a_template(id="first", target="A.md", render=lambda: "A\n"),
            a_template(id="second", target="docs/B.md", render=lambda: "B\n"),
        ],
    )
    (tmp_path / "docs").rmdir()
    (tmp_path / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(Refusal):
        apply(tmp_path, planned)
    assert (tmp_path / "A.md").read_text(encoding="utf-8") == "A\n"
    recorded = Manifest.read(tmp_path)
    assert recorded.get("first") is not None
    assert recorded.get("second") is None


def test_a_plan_carrying_a_refusal_creates_no_manifest_at_all(tmp_path: Path) -> None:
    # The boundary of persisting progress. `apply` refuses a plan carrying a refusal before it
    # reaches the first action, so there is nothing on disk to record and no ledger to create.
    config = a_config(tmp_path)
    planned = plan(tmp_path, config, [a_template(target="../outside.md")])
    with pytest.raises(Refusal, match="refused"):
        apply(tmp_path, planned)
    assert not (tmp_path / MANIFEST_PATH).exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the directory mode under test")
def test_a_file_that_cannot_be_unlinked_refuses_rather_than_raising_oserror(
    tmp_path: Path,
) -> None:
    # The removal half of "no bare OSError". `open_within` opens an r-x directory happily, so
    # EACCES arrives from `os.unlink` rather than as an `UnsafePath`, and the `suppress` around
    # the unlink is entered after the walk has yielded, so it covers neither.
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "OLD.md").write_text("BODY\n", encoding="utf-8")
    os.chmod(docs, stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(Refusal, match="cannot be removed"):
            engine._remove(tmp_path, "docs/OLD.md", None)
    finally:
        os.chmod(docs, 0o755)
    assert (docs / "OLD.md").exists()


# --- the two rules the module docstring is read for ------------------------------------------


def test_the_module_docstring_names_every_input_plan_raises_for() -> None:
    # A consumer reads this docstring to decide what to catch. It named two inputs while the
    # module raises for three: a `MANAGED_REGION` template carrying no region name is a malformed
    # `Template`, and the test above pins that `plan` deliberately does not soften it into a
    # per-artifact refusal.
    prose = " ".join((engine.__doc__ or "").split())
    assert "and a malformed `Template`" in prose
    assert "the configured profile, and the manifest itself" not in prose


def test_the_containment_docstring_claims_the_property_the_walk_actually_holds() -> None:
    # A component certainly can become a symlink after `contained()` has passed — two tests
    # above plant one for exactly that reason — so "there is no window" described a guarantee
    # nothing provides. What the O_NOFOLLOW walk holds is narrower and is the thing that
    # matters: the link cannot redirect the write.
    prose = " ".join((engine.__doc__ or "").split())
    assert "it cannot redirect the write" in prose
    assert "there is no window in which a component can become a symlink" not in prose
