"""`attach` links the store into the owning checkout and into every worktree that already exists.

The main checkout is `worktree.attach_main`'s (the case `link` excludes); every other checkout
is `worktree.link`'s, unchanged. This module asserts that `attach` reaches both.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from keelline.attach.api import Attached, attach
from keelline.config.loader import load
from keelline.config.schema import Config
from keelline.memory.api import PartialLink, harness_memory_path
from tests.attach.test_binding import CONFIG, _machine
from tests.attach.test_write import FakeRunner

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _git(root: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)


def _config(root: Path, machine: Path) -> Config:
    return load(root, machine=machine)


def _bound(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A committed repository in overlay mode, and the overlay that already records it."""
    root = tmp_path / "project"
    root.mkdir(parents=True)
    overlay = tmp_path / "overlay"
    (overlay / "common" / "memory").mkdir(parents=True)
    (overlay / "common" / "memory" / "shared.md").write_text("x", encoding="utf-8")
    own = overlay / "projects" / "p" / "memory"
    own.mkdir(parents=True)
    (own.parent / "project.toml").write_text(
        'remote = "git@example.com:o/p.git"\n', encoding="utf-8"
    )
    (overlay / "common" / "claude").mkdir(parents=True)
    (overlay / "common" / "codex").mkdir(parents=True)
    (root / "keelline.toml").write_text(CONFIG.format(name="p"), encoding="utf-8")
    (root / ".gitignore").write_text("docs/memory/\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "remote", "add", "origin", "git@example.com:o/p.git")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "init")
    return root, own, _machine(tmp_path, overlay=overlay)


def _attach(
    root: Path, store: Path, machine: Path, home: Path, *, confirmed: bool = False
) -> Attached:
    return attach(
        root,
        store=store,
        machine=machine,
        confirmed=confirmed,
        trust_remote=False,
        runner=FakeRunner(),
        home=home,
    )


def test_every_existing_worktree_is_linked(tmp_path: Path) -> None:
    # §6.3: "links memory into every existing worktree". A worktree created before the attach
    # is the common case — this repository has four of them. The main checkout is skipped here
    # because `attach_main` has already handled it, and `link` is a no-op there anyway.
    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    _attach(root, store, machine, tmp_path / "home")
    assert (root / "docs" / "memory" / "developer").is_symlink()
    assert (side / "docs" / "memory" / "developer").is_symlink()
    assert (side / "docs" / "memory" / "project-stable").is_symlink()


def test_a_partial_link_failure_leaves_attach_main_s_tree_on_disk_and_out_of_created(
    tmp_path: Path,
) -> None:
    # **This test pins a divergence, and its old name hid one.** `PartialLink` carries
    # `.created` precisely so a half-built tree is repairable rather than mysterious, and
    # `_link_everywhere`'s docstring says the exception propagates "with its `.created` intact".
    # It does not. That function accumulates `created` in a *local* list across `attach_main`
    # and one `link` per further checkout, and lets the exception out untouched — so what the
    # caller receives is the failing call's own list and nothing before it. Here that list is
    # empty while the owning checkout's link tree is on disk, which is precisely the state
    # `.created` exists to describe.
    #
    # The old assertions were these two, under the name "reports what it made": `created == []`
    # and "the main checkout's symlink exists". Read together they say the opposite of the name,
    # and the suite was green on both. Nothing consumes `.created` out of `attach` today —
    # `memory.hooks` catches `PartialLink` from `link` directly, where the list *is* intact — so
    # this is a latent defect and a false docstring rather than a live one, and fixing it is a
    # change to `attach`, which is another dispatch's file. Asserted as it behaves, named for
    # what it behaves like, and reported.
    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    real = Path.symlink_to

    def refuse_inside_the_worktree(
        self: Path, target: Path, target_is_directory: bool = False
    ) -> None:
        if str(self).startswith(str(side)):
            raise OSError("this filesystem refuses symlinks")
        real(self, target, target_is_directory=target_is_directory)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "symlink_to", refuse_inside_the_worktree)
        with pytest.raises(PartialLink) as failed:
            _attach(root, store, machine, tmp_path / "home")
    # The owning checkout's tree exists — `attach_main` made it before the failing call.
    made_by_attach_main = root / "docs" / "memory" / "developer"
    assert made_by_attach_main.is_symlink()
    # And is absent from the list the exception carries. The `== []` is deliberate and is the
    # whole finding: a caller repairing from `.created` would be told nothing was made.
    assert failed.value.created == []
    assert made_by_attach_main not in failed.value.created


def test_the_harness_fallback_is_recorded_so_it_can_be_withdrawn(tmp_path: Path) -> None:
    # §6.3 gives `~/.claude/projects/<slug>/memory` a fallback — `autoMemoryDirectory` in
    # settings.local.json — "because a settings-file value is subject to workspace trust and a
    # link is not". The symlink is preferred and the fallback is taken only when the link
    # cannot be made; when it is, it goes into the same ledger as everything else, because a
    # fallback nothing records is a setting that outlives its reason.
    import json

    from keelline.attach.api import ledger
    from keelline.memory.api import resolve
    from keelline.memory.trust import record

    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    # A real directory where the link belongs: the case `_link` refuses to clobber, and the one
    # §6.3 names alongside a filesystem that has no symlinks.
    harness = harness_memory_path(root, home)
    harness.mkdir(parents=True)
    attached = _attach(root, store, machine, home)
    settings = json.loads((root / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    assert settings["autoMemoryDirectory"] == str(resolved.path.resolve())
    assert ledger(root).settings_keys == ("autoMemoryDirectory",)
    assert any("autoMemoryDirectory" in note for note in attached.notes)


def _settings(root: Path) -> dict[str, object]:
    import json

    path = root / ".claude" / "settings.local.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _trusted(root: Path, machine: Path) -> None:
    from keelline.memory.api import resolve
    from keelline.memory.trust import record

    config = _config(root, machine)
    store = resolve(root, config, machine=machine)
    assert store is not None
    record(store, config)


def test_a_second_attach_neither_forgets_the_fallback_nor_lets_it_outlive_its_reason(
    tmp_path: Path,
) -> None:
    # `memory/worktree.py`'s own rule, one function over: "a gate evaluated once, at creation,
    # over state that persists is not a gate". A settings value is exactly such state, and this
    # is the channel that module calls "the one hop that leaves this lane's gate" — read by the
    # harness's native reader, outside every delimiter and trust record this lane controls.
    #
    # The sequence measured: attach with a real directory where the link belongs, so the
    # fallback is taken and recorded; then a `git pull` adds a note, which lapses the trust
    # record. `_apply_harness_link` correctly revokes the *symlink* channel — and the key used
    # to survive, with `_write_ledger` handed `()` on every run so the ledger forgot it too. The
    # harness went on reading the new bytes through a setting nothing recorded and `detach`
    # could no longer remove.
    #
    # Mutation: `mutations.toml`'s "the settings fallback outlives the gate that allowed it" —
    # make `_harness_fallback` return early when the link is no longer needed.
    from keelline.attach.api import ledger

    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    _trusted(root, machine)
    harness_memory_path(root, home).mkdir(parents=True)
    _attach(root, store, machine, home)
    # Non-vacuous: the rest of this is only about a lapse if the fallback was taken at all.
    assert "autoMemoryDirectory" in _settings(root)
    assert ledger(root).settings_keys == ("autoMemoryDirectory",)

    (tmp_path / "overlay" / "common" / "memory" / "pulled.md").write_text("# n\n", "utf-8")
    _attach(root, store, machine, home)
    assert "autoMemoryDirectory" not in _settings(root)
    assert ledger(root).settings_keys == ()


def test_the_fallback_goes_when_the_symlink_it_stood_in_for_can_be_made(tmp_path: Path) -> None:
    # The other arm of the same gate, and the one that needs no trust record to lapse. The
    # fallback exists only "when the link cannot be made"; once the real directory in the way is
    # gone the link is made and the setting has no reason left. It used to be left in the file
    # while the ledger was reset to `[]` around it, so `detach` left it behind for good — two
    # readers pointed at the store, one of them recorded nowhere.
    from keelline.attach.api import ledger

    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    _trusted(root, machine)
    harness = harness_memory_path(root, home)
    harness.mkdir(parents=True)
    _attach(root, store, machine, home)
    assert "autoMemoryDirectory" in _settings(root)

    harness.rmdir()
    _attach(root, store, machine, home)
    assert harness.is_symlink()
    assert "autoMemoryDirectory" not in _settings(root)
    assert ledger(root).settings_keys == ()


def test_a_second_attach_that_changes_nothing_still_records_the_standing_fallback(
    tmp_path: Path,
) -> None:
    # The vacuity guard for the two cases above: a `_harness_fallback` that simply never
    # recorded the key would pass both. While the real directory is still in the way, every
    # later attach must go on recording the key that is still in the file — which is the defect
    # in its original direction, since the ledger is what `detach` reads.
    from keelline.attach.api import ledger

    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    _trusted(root, machine)
    harness_memory_path(root, home).mkdir(parents=True)
    _attach(root, store, machine, home)
    _attach(root, store, machine, home)
    assert "autoMemoryDirectory" in _settings(root)
    assert ledger(root).settings_keys == ("autoMemoryDirectory",)


def test_attaching_from_a_linked_worktree_links_the_main_checkout_too(tmp_path: Path) -> None:
    # §6.3 asks for every checkout, and `--root` is allowed to name any of them. `attach_main`
    # used to be applied to whatever `--root` named and the loop then skipped
    # `main_checkout(root)` unconditionally — and `worktree.link` is documented as a no-op for
    # the main checkout, so nothing downstream caught it. Attaching from a worktree built that
    # worktree's tree and left the owning checkout with none: every session there saw no
    # memory, silently, and the command exited 0.
    #
    # Mutation: `mutations.toml`'s "attach applies the owning-checkout entry point to --root".
    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    _attach(side, store, machine, tmp_path / "home")
    assert (root / "docs" / "memory" / "developer").is_symlink()
    assert (root / "docs" / "memory" / "project-stable").is_symlink()
    assert (side / "docs" / "memory" / "developer").is_symlink()


def test_detaching_from_a_linked_worktree_withdraws_the_main_checkouts_tree_too(
    tmp_path: Path,
) -> None:
    # The mirror shape, and it had the mirror defect: `detach_main` was applied to `--root` and
    # the loop skipped the owner, so a detach run from a worktree withdrew that worktree's tree
    # twice and left the owning checkout's — and its harness link — in place.
    from keelline.attach.api import detach

    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    home = tmp_path / "home"
    # Attached from the worktree as well, because the ledger `detach` reads lives under
    # `.keelline/local/` in the checkout the attach was run from, and that directory is
    # untracked — a sibling worktree does not have one.
    _attach(side, store, machine, home)
    # Non-vacuous: there is nothing to withdraw unless both trees were built.
    assert (root / "docs" / "memory" / "developer").is_symlink()
    assert (side / "docs" / "memory" / "developer").is_symlink()
    detach(side, machine=machine, home=home)
    assert not (root / "docs" / "memory" / "developer").is_symlink()
    assert not (side / "docs" / "memory" / "developer").is_symlink()


def test_withdrawing_the_fallback_takes_the_settings_file_with_it_when_nothing_is_left(
    tmp_path: Path,
) -> None:
    # The one case in which `attach` removes a file, pinned rather than left to be discovered.
    # `{}` is not what `.claude/settings.local.json` looked like before the fallback was taken —
    # it is a file `attach` itself created — so the last thing withdrawn takes it away, which is
    # the rule `detach`'s own `_withdraw_settings` already applies and what keeps the round trip
    # byte-for-byte.
    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    _trusted(root, machine)
    harness = harness_memory_path(root, home)
    harness.mkdir(parents=True)
    _attach(root, store, machine, home)
    # Non-vacuous: the file exists, and the key is the only thing in it.
    assert list(_settings(root)) == ["autoMemoryDirectory"]

    harness.rmdir()
    _attach(root, store, machine, home)
    assert not (root / ".claude" / "settings.local.json").exists()


def test_withdrawing_the_fallback_never_takes_anything_else_out_of_that_file(
    tmp_path: Path,
) -> None:
    # The guard on the case above, and the one that matters: the removal may only ever fire when
    # Keelline's own key was the file's entire contents. An owner's own setting beside it keeps
    # the file, and keeps itself.
    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    (root / ".claude").mkdir(exist_ok=True)
    (root / ".claude" / "settings.local.json").write_text(
        '{\n  "permissions": {\n    "deny": [\n      "Bash(curl:*)"\n    ]\n  }\n}\n', "utf-8"
    )
    _attach(root, store, machine, home)
    _trusted(root, machine)
    harness = harness_memory_path(root, home)
    harness.mkdir(parents=True)
    _attach(root, store, machine, home)
    assert "autoMemoryDirectory" in _settings(root)

    harness.rmdir()
    _attach(root, store, machine, home)
    document = _settings(root)
    assert "autoMemoryDirectory" not in document
    permissions = document["permissions"]
    assert isinstance(permissions, dict)
    assert permissions["deny"] == ["Bash(curl:*)"]
