"""`keelline detach` removes exactly what `attach` added, and nothing else.

The ledger is the authority on what was ours. Guessing it back from the content of a settings
file is the heuristic the ledger exists to replace, and a detach built on a guess removes a rule
the owner wrote by hand — which is worse than removing none.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from keelline.attach.api import LEDGER, detach
from keelline.errors import Failure, Refusal
from keelline.memory.api import harness_memory_path, resolve
from keelline.memory.trust import record
from tests.attach.test_links import _attach, _bound, _config
from tests.attach.test_write import SETTINGS
from tests.test_install_path import _assert_snapshot_changed, _assert_snapshot_unchanged, _snapshot

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

RULE = "Bash(uv run pytest:*)"
ENTRY = {"type": "command", "command": "echo hello"}


def _grant(overlay: Path, *, allow: tuple[str, ...] = (), hooks: bool = False) -> None:
    claude = overlay / "common" / "claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "permissions.json").write_text(
        json.dumps({"permissions": {"allow": list(allow), "deny": []}}), encoding="utf-8"
    )
    (claude / "hooks.json").write_text(
        json.dumps({"hooks": {"SessionStart": [{"hooks": [ENTRY]}]} if hooks else {}}),
        encoding="utf-8",
    )
    (overlay / "common" / "codex").mkdir(parents=True, exist_ok=True)
    (overlay / "common" / "codex" / "common.rules").write_text("# rule\n", encoding="utf-8")


def _detach(root: Path, machine: Path, home: Path) -> object:
    return detach(root, machine=machine, home=home)


def test_detach_removes_exactly_what_attach_added(tmp_path: Path) -> None:
    # The round trip is the assertion: snapshot every file under the root, attach with
    # `confirmed=True`, detach, and compare against the snapshot. A detach that removes a rule
    # the owner wrote by hand is worse than one that removes none.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    before = _snapshot(root)
    _attach(root, store, machine, home, confirmed=True)
    _assert_snapshot_changed(root, before)
    _detach(root, machine, home)
    _assert_snapshot_unchanged(root, before)


def test_detach_leaves_a_rule_the_ledger_does_not_claim(tmp_path: Path) -> None:
    # Write an allow rule into settings.local.json by hand before attaching, attach, detach,
    # and assert that rule survives. The ledger is the authority on what was ours; content
    # heuristics are exactly what it exists to replace.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    (root / ".claude").mkdir(exist_ok=True)
    (root / SETTINGS).write_text(
        json.dumps({"permissions": {"allow": ["Bash(rm:*)"]}}), encoding="utf-8"
    )
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
    _detach(root, machine, home)
    document = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
    assert document["permissions"]["allow"] == ["Bash(rm:*)"]


def test_detach_leaves_a_hook_entry_that_was_never_marked(tmp_path: Path) -> None:
    # The same rule for the other half of the file. `scaffold.apply_entries` splits a group
    # rather than replacing it, so a developer's own entry beside Keelline's survives — and
    # this is the lane whose mistake would delete it.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], hooks=True)
    (root / ".claude").mkdir(exist_ok=True)
    (root / SETTINGS).write_text(
        json.dumps({"hooks": {"SessionStart": [{"hooks": [{"command": "mine.sh"}]}]}}),
        encoding="utf-8",
    )
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
    _detach(root, machine, home)
    document = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
    commands = [e["command"] for g in document["hooks"]["SessionStart"] for e in g["hooks"]]
    assert commands == ["mine.sh"]


def test_detach_without_a_ledger_says_so_and_changes_nothing(tmp_path: Path) -> None:
    # A repository attached by an older version, or by hand. Guessing which rules were ours
    # from their content is the heuristic this ledger exists to avoid, so the answer is a
    # `Failure` naming the missing ledger, not a best effort.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
    (root / LEDGER).unlink()
    before = _snapshot(root)
    # As in `test_a_mismatched_remote_refuses_and_writes_nothing`: `_snapshot` is a walk and an
    # empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Failure) as failed:
        _detach(root, machine, home)
    assert LEDGER in str(failed.value)
    _assert_snapshot_unchanged(root, before)


def test_detach_withdraws_the_harness_link(tmp_path: Path) -> None:
    # The link that leaves Keelline's gate is the one that must not outlive the binding — the
    # same asymmetry `worktree._unlink` already enforces in the other direction.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    _attach(root, store, machine, home)
    harness = harness_memory_path(root, home)
    assert harness.is_symlink()
    _detach(root, machine, home)
    assert not harness.is_symlink()
    assert not (root / "docs" / "memory" / "developer").is_symlink()


def test_detach_withdraws_the_link_tree_from_every_worktree(tmp_path: Path) -> None:
    # `attach` links into every existing worktree, so a detach that only cleaned the owning
    # checkout would leave every other one reading an overlay it is no longer bound to.
    import os
    import subprocess

    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    side = tmp_path / "side"
    subprocess.run(
        ["git", "worktree", "add", "-q", str(side), "-b", "side"],
        cwd=root,
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull},
    )
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    assert (side / "docs" / "memory" / "developer").is_symlink()
    _detach(root, machine, home)
    assert not (side / "docs" / "memory" / "developer").is_symlink()


def test_detach_withdraws_the_settings_fallback_it_recorded(tmp_path: Path) -> None:
    # The fallback is a setting, not a link, so nothing expires it: if `detach` left it behind
    # the harness would keep reading the store of a repository that is no longer bound.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    harness_memory_path(root, home).mkdir(parents=True)
    _attach(root, store, machine, home)
    assert "autoMemoryDirectory" in (root / SETTINGS).read_text(encoding="utf-8")
    _detach(root, machine, home)
    assert not (root / SETTINGS).exists()


def test_detach_leaves_the_binding_record_in_place(tmp_path: Path) -> None:
    # `projects/<name>/project.toml` is a record of the owner's consent, not a piece of local
    # state. Re-attaching later must not re-ask for it, and a detach that deleted it would
    # turn every re-attach into a first attach.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    _detach(root, machine, home)
    assert (store.parent / "project.toml").is_file()
    assert (store.parents[2] / "common" / "memory" / "shared.md").is_file()


def test_detach_removes_a_rule_file_the_overlay_has_since_deleted(tmp_path: Path) -> None:
    # §6.3 asks for "idempotent and reversible by `detach`", and the ledger is the only record
    # of what was placed. A rule file deleted from the overlay between two attaches is not
    # written by the second one and so drops out of a ledger built from that run alone — while
    # the copy the first attach made is still in `.codex/rules/`, where Codex reads it as a
    # standing instruction. Without the union, `detach` leaves it there for good.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    landed = root / ".codex" / "rules" / "common.rules"
    assert landed.is_file()
    (store.parents[2] / "common" / "codex" / "common.rules").unlink()
    _attach(root, store, machine, home)
    assert landed.is_file(), "the copy the first attach made is still here"
    _detach(root, machine, home)
    assert not landed.exists()


def _rewrite_ledger(root: Path, **fields: object) -> None:
    """The ledger a clone committed: `attach`'s own, with fields replaced.

    Built from a real one rather than by hand so that the case differs from a working detach in
    exactly the field under test. `.gitignore` does not untrack a file a clone committed, which
    is what makes this a state a fresh checkout can be in rather than a contrivance.
    """
    document = json.loads((root / LEDGER).read_text(encoding="utf-8"))
    document.update(fields)
    (root / LEDGER).write_text(json.dumps(document), encoding="utf-8")


def test_a_ledger_naming_a_file_attach_could_not_have_written_removes_nothing(
    tmp_path: Path,
) -> None:
    # The ledger is a record, not an authority. `fsops.remove_within` contains the removal to
    # the root — and `.github/workflows/`, `.pre-commit-config.yaml` and every source file are
    # inside it, so containment is not the guard that matters. The guard is that `attach` only
    # ever writes `.codex/rules/<file>`, so anything else in `rules` is a repository asking for
    # a deletion no attach could have earned.
    #
    # Mutation: `mutations.toml`'s "detach deletes whatever the ledger names" — make
    # `_rule_is_writable` answer True unconditionally and the workflow file goes.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("on: push\n", encoding="utf-8")
    _rewrite_ledger(root, rules=[".github/workflows/ci.yml", ".codex/rules/common.rules"])
    before = _snapshot(root)
    # `_snapshot` is a walk, and an empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Refusal):
        _detach(root, machine, home)
    _assert_snapshot_unchanged(root, before)
    assert workflow.is_file()


def test_a_ledger_claiming_the_permissions_key_never_drops_the_owners_deny_rules(
    tmp_path: Path,
) -> None:
    # The measured widening, and the reason this refusal is not a nicety. `_withdraw_settings`
    # assigns `raw["permissions"] = permissions` and *then* pops every string in
    # `settings_keys`, so a committed `settings_keys = ["permissions"]` took the owner's whole
    # permissions block out — deny rules included. A repository cannot be allowed to remove a
    # deny rule by committing a JSON file, whatever it calls that file.
    #
    # Mutation: the same entry as above, on the `settings_keys` half — let `_checked` accept a
    # key other than `autoMemoryDirectory` and the deny rule below is gone.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    (root / ".claude").mkdir(exist_ok=True)
    (root / SETTINGS).write_text(
        json.dumps({"permissions": {"allow": ["Bash(ls:*)"], "deny": ["Bash(curl:*)"]}}),
        encoding="utf-8",
    )
    _rewrite_ledger(root, settings_keys=["permissions"])
    with pytest.raises(Refusal):
        _detach(root, machine, home)
    document = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
    assert document["permissions"]["deny"] == ["Bash(curl:*)"]
    assert document["permissions"]["allow"] == ["Bash(ls:*)"]


def test_the_two_values_attach_really_writes_are_still_acted_on(tmp_path: Path) -> None:
    # The vacuity guard for both refusals above: a validator that refused everything would pass
    # them and break the command. A ledger holding exactly what `attach` wrote — one
    # `.codex/rules/` file and the one fallback key — detaches, and both are withdrawn.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    harness_memory_path(root, home).mkdir(parents=True)
    _attach(root, store, machine, home)
    from keelline.attach.api import ledger as read_ledger

    recorded = read_ledger(root)
    assert recorded.rules == (".codex/rules/common.rules",)
    assert recorded.settings_keys == ("autoMemoryDirectory",)
    _detach(root, machine, home)
    assert not (root / ".codex" / "rules" / "common.rules").exists()
    assert not (root / SETTINGS).exists()
