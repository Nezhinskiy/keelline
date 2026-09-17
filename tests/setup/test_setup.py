# tests/setup/test_setup.py
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from keelline.attach.api import read_binding
from keelline.errors import Refusal
from keelline.memory.api import overlay_root
from keelline.overlay.api import Completed
from keelline.presets import load_preset
from keelline.setup.api import USER_SETTINGS, read_machine, setup

# The minimal `keelline.toml` `attach.read_binding` needs (a project name and nothing else),
# the same shape `tests/setup/test_machine.py::_initialised_project` uses for `load()`.
CONFIG = """
[keelline]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"
"""


def _initialised_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "keelline.toml").write_text(CONFIG, encoding="utf-8")
    return project


@dataclass
class FakeRunner:
    """Records every argv `setup` would run, so an assertion is about the command and not a
    mock's return value — the same shape `tests/overlay/test_create.py::FakeRunner` uses; not
    imported from there because `tests/` is not a package (CONTRIBUTING, no cross-module test
    imports)."""

    answers: dict[str, Completed] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)
    on_call: Callable[[list[str], Path], None] | None = None

    def run(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append(argv)
        if self.on_call is not None:
            self.on_call(argv, cwd)
        return self.answers.get(argv[0], Completed(0, "", ""))


def _populate_overlay(argv: list[str], cwd: Path) -> None:
    """Stand in for a successful template generation, the same probe `overlay.create` reads."""
    if argv[:3] != ["gh", "repo", "create"]:
        return
    target = cwd / argv[3].split("/")[-1] / ".claude-plugin"
    target.mkdir(parents=True, exist_ok=True)
    (target / "plugin.json").write_text(json.dumps({"name": "keelline-overlay"}), encoding="utf-8")
    (target / "marketplace.json").write_text(
        json.dumps({"name": "keelline-overlay-marketplace", "plugins": []}), encoding="utf-8"
    )


def test_setup_writes_the_machine_file_and_the_deny_rules(tmp_path: Path) -> None:
    # Two machine-level writes, both enumerated by D14. Assert the machine file round-trips
    # through `read_machine`, and that `<home>/.claude/settings.json` — `setup.api.USER_SETTINGS`,
    # the one machine-scope settings file this plan writes — carries every rule from the
    # preset's `[deny] global` and no `allow` key at all.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    setup("recommended", home=home, machine=machine, runner=FakeRunner(), yes=True, overlay=None)
    written = read_machine(machine)
    assert written["personal"]["artifact_language"] == "en"
    settings = json.loads((home / USER_SETTINGS).read_text(encoding="utf-8"))
    preset = load_preset("recommended")
    for rule in preset["deny"]["global"]:
        assert rule in settings["permissions"]["deny"]
    assert "allow" not in settings.get("permissions", {})


def test_an_existing_user_settings_file_keeps_the_owners_own_rules(tmp_path: Path) -> None:
    # The owner's `~/.claude/settings.json` is theirs and predates Keelline on most machines.
    # Merge, never replace, and record nothing about entries this run did not add. Mutation:
    # `_write_user_settings`'s `existing_deny = (...)` line changed to always start from `[]`
    # → reddens on the dropped `Read(/etc/shadow)` rule.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    own = {"permissions": {"deny": ["Read(/etc/shadow)"]}, "theme": "dark"}
    (home / USER_SETTINGS).write_text(json.dumps(own), encoding="utf-8")
    setup(
        "recommended",
        home=home,
        machine=tmp_path / "config.toml",
        runner=FakeRunner(),
        yes=True,
        overlay=None,
    )
    settings = json.loads((home / USER_SETTINGS).read_text(encoding="utf-8"))
    assert "Read(/etc/shadow)" in settings["permissions"]["deny"]
    assert settings["theme"] == "dark"


def test_every_plugin_install_is_one_recorded_argv(tmp_path: Path) -> None:
    # The Runner seam again. What can be wrong here is the selector, and only an argv assertion
    # can see it — Findings → S6 measured that an owner-suffixed selector installs, which is
    # exactly the kind of string a mocked subprocess would have hidden.
    runner = FakeRunner()
    setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=runner,
        yes=True,
        overlay=None,
    )
    preset = load_preset("recommended")
    for selector in preset["plugins"]["install"]:
        assert ["claude", "plugin", "install", selector, "--scope", "user", "-y"] in runner.calls
        # Findings → Task 1/Task 2 of the spike record: Codex adds a plugin, it does not
        # install one.
        assert ["codex", "plugin", "add", selector] in runner.calls


def test_a_harness_that_is_not_installed_is_a_note_not_a_failure(tmp_path: Path) -> None:
    # `agents = ["claude", "codex"]` is the default and most machines have one of the two.
    # Refusing to set up a machine because Codex is absent would be absurd.
    runner = FakeRunner(answers={"codex": Completed(127, "", "codex: command not found")})
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=runner,
        yes=True,
        overlay=None,
    )
    assert any("codex" in note for note in report.notes)


def test_the_overlay_offer_is_never_taken_without_being_asked(tmp_path: Path) -> None:
    # §6.1: `overlay create` runs `gh repo create` "after explicit confirmation". A default
    # that creates a GitHub repository is the one default this command may not have — and
    # `--yes`, which takes the detected defaults for everything else, must not take this one.
    runner = FakeRunner()
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=runner,
        yes=True,
        overlay=None,
    )
    assert report.overlay is None
    assert not any(argv[:2] == ["gh", "repo"] for argv in runner.calls)


def test_pointing_at_an_existing_overlay_records_its_root_and_creates_nothing(
    tmp_path: Path,
) -> None:
    # The second of the three answers §8.1's question 2 offers, and the answer a second machine
    # gives: the overlay already exists and is cloned, and `setup` only records it.
    existing = tmp_path / "overlay"
    existing.mkdir()
    machine = tmp_path / "config.toml"
    runner = FakeRunner()
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=machine,
        runner=runner,
        yes=True,
        overlay=str(existing),
    )
    assert report.overlay == existing
    assert not any(argv[:2] == ["gh", "repo"] for argv in runner.calls)
    assert overlay_root(machine) == existing


def test_overlay_create_asks_github_and_records_the_new_root(tmp_path: Path) -> None:
    # The first of §8.1's three answers: nothing exists yet, so `setup` both creates the
    # repository and records what it created — the same probe `overlay.create` uses
    # (`.claude-plugin`) is what tells this test the create branch, and not a no-op, ran.
    #
    # `home`, and not `Path.cwd()`, is asserted here rather than merely the leaf name: measured
    # while writing this module, `root=Path.cwd()` created a real `keelline-private/` inside
    # this checkout the first time this branch ran under a test, because `tmp_path` was never
    # in that call at all. Mutation: change `_apply_overlay`'s `root=home` back to
    # `root=Path.cwd()` → reddens on this line without touching the `.name` check alone.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    runner = FakeRunner(on_call=_populate_overlay)
    report = setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay="create:octo/keelline-private",
    )
    assert any(argv[:3] == ["gh", "repo", "create"] for argv in runner.calls)
    assert report.overlay == home / "keelline-private"
    assert overlay_root(machine) == report.overlay


def test_the_recorded_overlay_root_is_what_attach_then_refuses_outside_of(tmp_path: Path) -> None:
    # The C→D seam, asserted rather than assumed — and asserted through the refusal, which is
    # the half that matters: run `setup --overlay <path>`, then call `attach.read_binding` with
    # a `--store` under a different directory and expect `Refusal`. DP3's anchor is only real
    # if the value `setup` writes is the value `attach` reads.
    #
    # No new mutations.toml entry: the guard this exercises is `binding.py`'s own
    # store-must-match-`permitted_roots` check, already load-bearing there under "the overlay
    # root comes from the machine file and not from the argument" — this test proves the two
    # ends of the seam agree, not a new line to mutate.
    existing = tmp_path / "overlay"
    existing.mkdir()
    machine = tmp_path / "config.toml"
    setup(
        "recommended",
        home=tmp_path / "home",
        machine=machine,
        runner=FakeRunner(),
        yes=True,
        overlay=str(existing),
    )
    project = _initialised_project(tmp_path)
    wrong_store = tmp_path / "elsewhere" / "memory"
    with pytest.raises(Refusal):
        read_binding(project, store=wrong_store, machine=machine)


def test_a_second_run_is_idempotent(tmp_path: Path) -> None:
    # Two runs, one report each; the second installs no plugin twice and leaves the deny list
    # the same length.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    runner = FakeRunner()
    first = setup("recommended", home=home, machine=machine, runner=runner, yes=True, overlay=None)
    second = setup("recommended", home=home, machine=machine, runner=runner, yes=True, overlay=None)
    assert sorted(first.plugins_installed) == sorted(second.plugins_installed)
    settings = json.loads((home / USER_SETTINGS).read_text(encoding="utf-8"))
    preset = load_preset("recommended")
    assert len(settings["permissions"]["deny"]) == len(preset["deny"]["global"])
