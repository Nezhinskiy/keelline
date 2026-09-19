from __future__ import annotations

import json
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run
from keelline.errors import Refusal
from keelline.overlay.api import create, init_instance
from keelline.overlay.upgrade import upgrade
from keelline.scaffold import MANIFEST_PATH, Verb, digest
from tests.overlay.test_create import FakeRunner


def _an_overlay(tmp_path: Path) -> Path:
    return create("octo", "ov", source="local", root=tmp_path, runner=FakeRunner()).root


def _restamp(root: Path, artifact_id: str) -> None:
    """Record the artifact's *current* bytes, the state a release leaves behind when the
    template has moved on and the instance has not."""
    path = root / MANIFEST_PATH
    document = json.loads(path.read_text(encoding="utf-8"))
    body = (root / artifact_id).read_text(encoding="utf-8")
    document["artifacts"][artifact_id]["sha256"] = digest(body)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def test_an_untouched_skeleton_file_is_refreshed(tmp_path: Path) -> None:
    # §6.1: "refreshes untouched skeleton files after a release by the project rule (§7.3)".
    # That rule is C2's hash comparison; this asserts the overlay really goes through it rather
    # than reimplementing it.
    root = _an_overlay(tmp_path)
    (root / "README.md").write_text("stale", encoding="utf-8")
    _restamp(root, "README.md")  # record the hash of the stale text, as a release would
    verbs = {a.artifact_id: a.verb for a in upgrade(root, dry_run=True).plan.actions}
    assert verbs["README.md"] is Verb.UPDATE


def test_a_hand_edited_file_is_skipped_and_named(tmp_path: Path) -> None:
    # The same rule's other half. An overlay is where the owner's own rules live, so a silent
    # overwrite here destroys the only copy of something.
    root = _an_overlay(tmp_path)
    (root / "common" / "codex" / "common.rules").write_text("my own rules\n", encoding="utf-8")
    verbs = {a.artifact_id: a.verb for a in upgrade(root, dry_run=True).plan.actions}
    assert verbs["common/codex/common.rules"] is Verb.SKIP_MODIFIED


def test_the_two_permission_files_are_asked_about_even_when_unchanged(tmp_path: Path) -> None:
    # §6.1 names exactly two exceptions to the hash rule, "which it diffs and asks about
    # regardless of hash" — they are the two files that can grant capability, and a hash match
    # is not consent for those. C2 has no verb for it and is frozen, so the decision list lives
    # beside the plan rather than inside it.
    root = _an_overlay(tmp_path)
    decisions = upgrade(root, dry_run=True).decisions
    assert set(decisions) == {"common/claude/permissions.json", "common/claude/hooks.json"}


def test_a_dry_run_writes_nothing_where_a_real_run_would(tmp_path: Path) -> None:
    # Non-vacuous on purpose: on a freshly created overlay the plan carries no action, so a dry
    # run and a real run both write nothing and `if not dry_run:` could be deleted unnoticed.
    # A stale, re-stamped file gives the plan an UPDATE; the dry run must leave the stale bytes
    # and the real run must replace them. Mutation: `if not dry_run:` → `if True:` reddens the
    # first assertion; `apply(...)` removed reddens the second.
    root = _an_overlay(tmp_path)
    (root / "README.md").write_text("stale", encoding="utf-8")
    _restamp(root, "README.md")
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert upgrade(root, dry_run=True).plan.actions
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
    upgrade(root, dry_run=False)
    assert (root / "README.md").read_text(encoding="utf-8") != "stale"


def test_a_directory_that_is_not_an_overlay_is_refused_before_anything_is_written(
    tmp_path: Path,
) -> None:
    # Review finding 10. `--root` defaults to `.` and was checked nowhere: in a directory
    # holding a `README.md` and a `src/main.py`, `keelline overlay upgrade --root .` created
    # fourteen files — both plugin manifests, `hooks/hooks.json`, `common/**`, `.gitignore` and
    # `.github/workflows/scan.yml` — printed `14 to create` and exited 0. Writing a workflow
    # file into a repository the owner may then commit is the concrete harm.
    #
    # Mutation (`mutations.toml`, "overlay upgrade stops asking whether --root is an overlay"):
    # the `require_overlay` call is removed → the fourteen files appear and this reddens on both
    # the refusal and the tree.
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "README.md").write_text("# a project, not an overlay\n", encoding="utf-8")
    (project / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    before = sorted(p.relative_to(project) for p in project.rglob("*"))
    assert before, "the fixture writes nothing, so the comparison below would prove nothing"
    with pytest.raises(Refusal, match="must name an overlay"):
        upgrade(project, dry_run=False)
    assert sorted(p.relative_to(project) for p in project.rglob("*")) == before


def test_the_cli_exits_two_rather_than_zero_on_a_directory_that_is_not_an_overlay(
    tmp_path: Path,
) -> None:
    # The same finding through the command surface, which is where it was reproduced: the run
    # that created fourteen files reported them as work done and exited 0, so nothing about the
    # outcome said anything had gone wrong.
    (tmp_path / "README.md").write_text("# not an overlay\n", encoding="utf-8")
    parser = build_parser(discover_registrars())
    assert run(["overlay", "upgrade", "--root", str(tmp_path)], parser=parser) == 2
    assert [p.name for p in tmp_path.iterdir()] == ["README.md"]


def test_a_manifest_init_renamed_is_still_refreshed_by_a_later_release(tmp_path: Path) -> None:
    # Review finding 15. `overlay init` rewrote both manifests behind the scaffold ledger, so
    # every later `upgrade` reported `skip_modified .claude-plugin/plugin.json (hand-edited)` —
    # for the one file carrying `keelline.requires`, the version-compatibility declaration the
    # README advertises, and attributing to the owner an edit Keelline itself made. `init` now
    # re-stamps each record with the bytes it wrote.
    #
    # Mutation (`mutations.toml`, "overlay init writes the manifests behind the scaffold
    # ledger"): the `with_record(replace(...))` line stops updating the digest → both manifests
    # read as hand-edited and this reddens.
    root = _an_overlay(tmp_path)
    init_instance(root, "OctoCat", runner=FakeRunner())
    verbs = {a.artifact_id: a.verb for a in upgrade(root, dry_run=True).plan.actions}
    for manifest in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"):
        assert verbs[manifest] is not Verb.SKIP_MODIFIED
    # And the refresh really is live: a release that moves the template updates the file rather
    # than leaving the owner on a manifest nothing can reach.
    # Still a manifest that names this overlay — a release moving the file is what is being
    # modelled, not an owner breaking it — but with the older body a release has left behind.
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "keelline-overlay-octocat", "version": "0.0.0"}) + "\n",
        encoding="utf-8",
    )
    _restamp(root, ".claude-plugin/plugin.json")
    moved = {a.artifact_id: a.verb for a in upgrade(root, dry_run=True).plan.actions}
    assert moved[".claude-plugin/plugin.json"] is Verb.UPDATE
