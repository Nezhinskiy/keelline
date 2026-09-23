"""`keelline detach` removes exactly what `attach` added, and nothing else.

The ledger is the authority on what was ours. Guessing it back from the content of a settings
file is the heuristic the ledger exists to replace, and a detach built on a guess removes a rule
the owner wrote by hand — which is worse than removing none.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path, PurePosixPath

import pytest

from keelline.attach.api import LEDGER
from keelline.attach.write import GITIGNORE, IGNORE_BODY, IGNORE_REGION, Detached, detach
from keelline.errors import Failure, Refusal
from keelline.memory.api import harness_memory_path, resolve
from keelline.memory.trust import record
from keelline.scaffold import MANIFEST_PATH, Kind, Location, Manifest, Record, digest
from keelline.scaffold.regions import RegionError, Style, extract, markers, upsert
from tests.attach.test_binding import DEFAULT_MEMORY
from tests.attach.test_links import _attach, _bound, _config
from tests.attach.test_write import SETTINGS
from tests.gitfixture import git
from tests.snapshot import assert_snapshot_changed, assert_snapshot_unchanged, snapshot

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


def _detach(root: Path, machine: Path, home: Path) -> Detached:
    return detach(root, machine=machine, home=home)


def test_detach_removes_exactly_what_attach_added(tmp_path: Path) -> None:
    # The round trip is the assertion: snapshot every file under the root, attach with
    # `confirmed=True`, detach, and compare against the snapshot. A detach that removes a rule
    # the owner wrote by hand is worse than one that removes none.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    before = snapshot(root)
    _attach(root, store, machine, home, confirmed=True)
    assert_snapshot_changed(root, before)
    _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)


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
    before = snapshot(root)
    # As in `test_a_mismatched_remote_refuses_and_writes_nothing`: `snapshot` is a walk and an
    # empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Failure) as failed:
        _detach(root, machine, home)
    assert LEDGER in str(failed.value)
    assert_snapshot_unchanged(root, before)


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
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    side = tmp_path / "side"
    git(root, "worktree", "add", "-q", str(side), "-b", "side")
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
    before = snapshot(root)
    # `snapshot` is a walk, and an empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Refusal):
        _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)
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


def _a_git_that_cannot_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """A `git` that cannot be launched at all, at the seam `memory.store` runs it through.

    The state `GitUnavailable` exists for, and its own docstring says a review machine hit it.
    Patched rather than arranged, because the alternative is removing `git` from `PATH` for the
    whole process.
    """

    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("git: command not found")

    monkeypatch.setattr("keelline.memory.store.subprocess.run", refuse)


def test_a_git_that_cannot_run_is_answered_before_anything_is_withdrawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `detach` cannot refuse the way `attach` does once it has started — by the time it reaches
    # the link tree the settings and the rule files are gone, and refusing there strands a
    # half-detached repository. That is why `detach_main` checks `memory.mode` through the
    # target it derives rather than by refusing. It is not licence to *discover* a precondition
    # late: this one is a fact about the machine, true before the run began.
    #
    # `main_checkout` and `_worktrees` are the only things here that need `git`, and they sat
    # between the settings withdrawal and the link trees — so a machine whose `git` was gone got
    # exit 1 with `.claude/settings.local.json` and `.codex/rules/common.rules` already removed
    # and every link, the ignore region and the ledger still in place. Both are pure reads.
    #
    # Mutation: `mutations.toml`'s "detach asks git where the checkouts are after it has already
    # withdrawn".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
    before = snapshot(root)
    # `snapshot` is a walk, and an empty one satisfies the comparison below on its own.
    assert before
    _a_git_that_cannot_run(monkeypatch)
    with pytest.raises(Failure):
        _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)
    assert (root / "docs" / "memory" / "developer").is_symlink()


def test_the_git_failure_is_reached_on_a_run_that_would_have_withdrawn(tmp_path: Path) -> None:
    # The vacuity guard for the snapshot above: a refusal that withdraws nothing proves nothing
    # if the run had nothing to withdraw. The identical fixture, with a `git` that works,
    # withdraws every artifact the case above has to leave standing.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
    before = snapshot(root)
    assert before
    removed = _detach(root, machine, home)
    after = snapshot(root)
    gone = set(before) - set(after)
    assert {SETTINGS, ".codex/rules/common.rules", LEDGER} <= gone
    assert removed.allow_removed == (RULE,)
    assert not (root / "docs" / "memory" / "developer").is_symlink()


# --- the directories, which the file snapshot could not see -----------------------------------


def _directories(root: Path) -> set[str]:
    """Every directory under the root but `.git`, as `snapshot` would if it saw directories."""
    found: set[str] = set()
    for path in root.rglob("*"):
        if path.is_dir() and not path.is_symlink() and ".git" not in path.relative_to(root).parts:
            found.add(str(path.relative_to(root)))
    return found


def test_detach_removes_the_directories_the_attach_created(tmp_path: Path) -> None:
    # `docs/cli.md` promised "an attach and a detach leave the tree byte-for-byte as it was" and
    # it was false for directories: `.keelline/local/`, `.keelline/`, `.codex/rules/` and
    # `.codex/` survived every round trip. `snapshot` filters on `is_file()`, so the round-trip
    # test above passed while four directories accumulated.
    #
    # The set is asserted by value and not by `not any(...)`: a `_withdraw_directories` that
    # removed only the leaves, or only `.keelline/`, satisfies "something was removed" and
    # leaves the tree changed. `.claude/` is on the list too — the overlay here grants a rule,
    # so the attach creates it.
    #
    # Mutation: `mutations.toml`'s "detach leaves behind the directories the attach created".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    before = _directories(root)
    _attach(root, store, machine, home, confirmed=True)
    # The walk the comparison below rests on, asserted non-empty before it is trusted: an
    # `rglob` that finds nothing would satisfy every equality in this case on its own.
    assert _directories(root) > before
    removed = _detach(root, machine, home)
    assert set(removed.directories_removed) == {
        ".keelline/local",
        ".keelline",
        ".codex/rules",
        ".codex",
        ".claude",
    }
    # `paths.memory` is the documented exception and is named here so a lane that changes it has
    # to change this line: `worktree.detach_main` withdraws the links and not the directory that
    # held them, because that directory is repository-configured and may be one the project
    # keeps for its own reasons.
    memory = PurePosixPath(DEFAULT_MEMORY)
    assert _directories(root) - before == {str(memory), str(memory.parent)}


def _detach_after_attach(root: Path, store: Path, machine: Path, home: Path) -> Detached:
    _attach(root, store, machine, home, confirmed=True)
    return _detach(root, machine, home)


def test_detach_keeps_a_directory_that_still_holds_something(tmp_path: Path) -> None:
    # The floor under the ledger: the removal is `rmdir`, so a directory holding anything the
    # attach did not put there survives — and its parent survives with it, because a parent that
    # still holds a child is not empty either. A `shutil.rmtree` here would delete the owner's
    # own `.codex/rules/` file on a detach that promised to remove only what it added.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
    mine = root / ".codex" / "rules" / "zz-my-own.md"
    mine.write_text("# mine\n", encoding="utf-8")
    removed = _detach(root, machine, home)
    assert mine.is_file(), "a detach deleted a rule file the owner wrote by hand"
    assert ".codex/rules" not in removed.directories_removed
    assert ".codex" not in removed.directories_removed
    # And the ones that had nothing of the owner's in them still went.
    assert ".keelline" in removed.directories_removed


def test_detach_leaves_a_directory_that_was_there_before_the_attach(tmp_path: Path) -> None:
    # The other half, and the one the ledger answers rather than `rmdir`: an **empty** `.codex/`
    # the owner made themselves is indistinguishable from one this attach created, once the run
    # is over. `_absent_directories` is asked above the first write, so it is not on the ledger
    # and `detach` does not touch it — a detach must not remove a directory it did not create.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    (root / ".codex").mkdir()
    removed = _detach_after_attach(root, store, machine, home)
    assert (root / ".codex").is_dir(), "a detach removed a directory that predated the attach"
    assert ".codex" not in removed.directories_removed
    # `.codex/rules/` inside it was this attach's, and still goes.
    assert ".codex/rules" in removed.directories_removed
    assert not (root / ".codex" / "rules").exists()


def test_a_ledger_naming_a_directory_no_attach_creates_is_refused(tmp_path: Path) -> None:
    # `.keelline/local/attach.json` is a path a clone can commit, and `directories` drives
    # `rmdir`. It is held to the same closed list `rules` and `settings_keys` are held to, so a
    # ledger naming `src` is refused with nothing removed rather than obeyed — even though
    # `rmdir` would have spared a non-empty `src/` anyway. A partial defence reported as a
    # success is the shape this refusal exists to avoid.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
    recorded = json.loads((root / LEDGER).read_text(encoding="utf-8"))
    recorded["directories"] = ["src"]
    (root / LEDGER).write_text(json.dumps(recorded), encoding="utf-8")
    (root / "src").mkdir()
    before = snapshot(root)
    assert before
    with pytest.raises(Refusal):
        _detach(root, machine, home)
    assert (root / "src").is_dir()
    assert_snapshot_unchanged(root, before)


def test_a_home_whose_claude_became_a_symlink_refuses_above_every_withdrawal(
    tmp_path: Path,
) -> None:
    # The mirror of the `attach` case, and the half that had no answer at all: the walk's
    # `UnsafePath` left `detach` uncaught, `cli.run` rendered it as `internal error` and exit
    # 2, and every later `detach` failed at the same line — with `.codex/rules/` already
    # deleted and the ledger, the ignore region and every link still on disk. A repository no
    # shipped command could return to its pre-attach state.
    #
    # The layout is reached the way a person reaches it: attach first, then let the dotfiles
    # manager adopt `~/.claude`. That is also why this is `detach`'s case and not a repeat of
    # `attach`'s — the home directory was fine when the repository was attached.
    #
    # Mutation (declared, "detach discovers the harness anchor from inside the withdrawal"):
    # the hoisted loop goes -> the refusal still arrives, from `detach_main`, and
    # `assert_snapshot_unchanged` reddens with the rule files already removed.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    _attach(root, store, machine, home, confirmed=True)
    harness = harness_memory_path(root, home)
    assert harness.is_symlink(), "there is no harness link for this case to be about"
    adopted = tmp_path / "dotfiles" / "claude"
    adopted.parent.mkdir(parents=True)
    shutil.move(str(home / ".claude"), str(adopted))
    (home / ".claude").symlink_to(adopted, target_is_directory=True)
    before = snapshot(root)
    assert before
    with pytest.raises(Refusal) as refused:
        _detach(root, machine, home)
    assert str(home / ".claude") in str(refused.value)
    # Nothing was withdrawn, so the repository is still the one the attach left and a second
    # `detach` — against a home whose `.claude` is a real directory — still has everything to
    # withdraw.
    assert_snapshot_unchanged(root, before)
    assert (root / LEDGER).is_file()
    assert (root / ".codex" / "rules").is_dir()
    assert harness.is_symlink()


def test_a_gitignore_region_that_cannot_be_withdrawn_is_answered_before_anything_is(
    tmp_path: Path,
) -> None:
    # The same shape as the `git` case above, one precondition over. `drop()` refuses a region
    # opened twice — what a merge that kept both sides leaves — and it was asked *after* the
    # settings withdrawal, the rule files and every link tree: rules gone, links gone, ledger
    # still there, `doctor` still reporting the repository attached, and a second `detach`
    # failing at the same line. The region is now read beside the ledger and `_checkouts`, so a
    # broken one refuses above the first withdrawal.
    #
    # Mutation (`mutations.toml`, "detach reads the ignore region after it has already
    # withdrawn"): the remainder computed where the write happens → the snapshot below changes.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
    begin, _end = markers(IGNORE_REGION, Style.HASH)
    ignore = root / GITIGNORE
    ignore.write_text(f"{begin}\n" + ignore.read_text(encoding="utf-8"), encoding="utf-8")
    before = snapshot(root)
    with pytest.raises(RegionError):
        _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)
    assert (root / LEDGER).is_file()
    assert (root / "docs" / "memory" / "developer").is_symlink()


def test_a_whitespace_only_gitignore_survives_the_round_trip(tmp_path: Path) -> None:
    # `docs/cli.md` promises the round trip is byte-for-byte, and the withdrawal removed the
    # file whenever what remained was blank — so a `.gitignore` holding one newline before the
    # attach was gone after the detach. Only a file the attach created is taken away.
    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    (root / GITIGNORE).write_text("\n", encoding="utf-8")
    before = snapshot(root)
    _attach(root, store, machine, home)
    _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)
    assert (root / GITIGNORE).read_bytes() == b"\n"


def test_a_region_init_recorded_survives_a_detach(tmp_path: Path) -> None:
    """DC4: ownership decides, not last writer.

    `keelline init` records the `keelline:ignore` region as a footprint artifact with exactly
    the body `attach` writes — one spelling, imported rather than respelled, so neither command
    can report the other's region as hand-edited. `attach`'s own write stays and is idempotent;
    what changes is the withdrawal. A `detach` that dropped a region the manifest records would
    take a line out of a *committed* file that `init` put there, and `upgrade` would then read
    the footprint as hand-edited on a repository nobody edited.

    The manifest is the authority because it is the only record of who wrote the region that
    survives the region being written twice. There is no new ledger field: the attach ledger is
    per-checkout and untracked, and the question "whose region is this" is answered for every
    clone by the committed manifest.

    Mutation: `mutations.toml`'s "detach withdraws a region the footprint owns".
    """
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    (root / GITIGNORE).write_text(
        "node_modules/\n" + upsert("", IGNORE_REGION, IGNORE_BODY, Style.HASH), encoding="utf-8"
    )
    Manifest(
        {
            "gitignore": Record(
                "gitignore",
                Kind.MANAGED_REGION,
                Location.REPO,
                GITIGNORE,
                "gitignore",
                "0.1.0",
                digest(IGNORE_BODY),
            )
        }
    ).write(root)
    _attach(root, store, machine, tmp_path / "home", confirmed=True)
    removed = _detach(root, machine, tmp_path / "home")
    text = (root / GITIGNORE).read_text(encoding="utf-8")
    assert removed.ignore_region_removed is False
    assert text.startswith("node_modules/\n")
    assert extract(text, IGNORE_REGION, Style.HASH) == IGNORE_BODY


def _newer_format(manifest: Path, outside: Path) -> None:
    manifest.write_text(json.dumps({"format": 99}), encoding="utf-8")


def _not_utf8(manifest: Path, outside: Path) -> None:
    manifest.write_bytes(b'{"a": "\xff"}')


def _nested_past_the_stack(manifest: Path, outside: Path) -> None:
    manifest.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")


def _symlinked_out_of_the_root(manifest: Path, outside: Path) -> None:
    outside.write_text("{}", encoding="utf-8")
    manifest.symlink_to(outside)


@pytest.mark.parametrize(
    "commit",
    [_newer_format, _not_utf8, _nested_past_the_stack, _symlinked_out_of_the_root],
    ids=lambda commit: commit.__name__.lstrip("_"),
)
def test_a_manifest_a_clone_committed_cannot_block_the_withdrawal(
    tmp_path: Path, commit: Callable[[Path, Path], None]
) -> None:
    """A repository may not disable the command that undoes an attach.

    `.keelline/manifest.json` is **tracked** -- the ignore region covers `.keelline/local/` and
    `.keelline/assessment.json` and nothing else -- so a clone commits whatever it likes there,
    and `Manifest.read` refuses one that is unreadable, is not an object, or declares a `format`
    past this Keelline's. `attach` never reads the file, so a clone shipping `{"format": 99}`
    attached cleanly, merged the owner's allow rules and hook entries, and then made `detach`
    exit 2 on every run for ever: the ownership question is asked above every withdrawal, so
    nothing was half-undone and nothing could ever be undone either.

    Refusing with a better sentence is not the answer, because the act it would name is
    "delete a tracked file out of somebody else's repository". An unreadable manifest is read
    as no claim this command will act on and no claim it will act against: the region stays,
    which is the conservative half, and the detach finishes. Everything else comes back, which
    is what the settings file and the ledger assert here.

    The first fix caught `ManifestError` alone, and a clone has three other ways to make the
    read fail: bytes that are not UTF-8 (`UnicodeDecodeError`, a `ValueError` the reader did not
    name), nesting deep enough to exhaust the parser's stack (`RecursionError`), and a manifest
    committed as a symlink out of the root (`PathEscape`, raised before any byte is read). Each
    one made the detach exit 2 exactly as `{"format": 99}` had.

    Mutations: `mutations.toml`'s "an unreadable manifest blocks the detach again" and "the
    manifest reader lets undecodable bytes out as a crash again".
    """
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
    assert (root / LEDGER).is_file()
    # Written after the attach, exactly as a clone's committed one is there before a later
    # `detach` and never read by the run that wrote the ledger.
    manifest = root / MANIFEST_PATH
    manifest.parent.mkdir(parents=True, exist_ok=True)
    commit(manifest, tmp_path / "outside.json")
    removed = _detach(root, machine, home)
    assert not (root / LEDGER).exists()
    assert removed.allow_removed == (RULE,)
    # The conservative half: ownership could not be established, so the block is left alone and
    # the result says so rather than claiming a withdrawal it did not make.
    assert removed.ignore_region_removed is False
    assert extract((root / GITIGNORE).read_text(encoding="utf-8"), IGNORE_REGION, Style.HASH)
