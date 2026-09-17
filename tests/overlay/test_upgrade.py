from __future__ import annotations

import json
from pathlib import Path

from keelline.overlay.api import create, upgrade
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


def test_a_dry_run_writes_nothing(tmp_path: Path) -> None:
    root = _an_overlay(tmp_path)
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    upgrade(root, dry_run=True)
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
