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
from keelline.overlay.api import MARKETPLACE_MANIFEST, PLUGIN_MANIFEST, Completed
from keelline.presets import load_preset
from keelline.setup.api import USER_SETTINGS, read_machine, setup, write_machine

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


def _seed_overlay(path: Path) -> None:
    """Give `path` the two manifests `_validate_overlay_root` checks for, without rendering the
    whole template — enough for a fixture to read as a real overlay's root."""
    (path / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (path / PLUGIN_MANIFEST).write_text(json.dumps({"name": "keelline-overlay"}), encoding="utf-8")
    (path / MARKETPLACE_MANIFEST).write_text(
        json.dumps({"name": "keelline-overlay-marketplace", "plugins": []}), encoding="utf-8"
    )


def test_setup_writes_the_machine_file_and_the_deny_rules(tmp_path: Path) -> None:
    # Two machine-level writes, both enumerated by D14. Assert the machine file round-trips
    # through `read_machine`, and that `<home>/.claude/settings.json` — `setup.api.USER_SETTINGS`,
    # the one machine-scope settings file this plan writes — carries every rule from the
    # preset's `[deny] global` and no `allow` key at all.
    #
    # Mutation: `_write_user_settings`'s `permissions["deny"] = ...` line changed to write
    # `permissions["allow"]` instead → reddens both assertions below (the deny list goes missing
    # and an allow key appears) — the exact typo the deny-only invariant exists to catch.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=FakeRunner(),
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
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
        project_root=tmp_path / "project",
    )
    settings = json.loads((home / USER_SETTINGS).read_text(encoding="utf-8"))
    assert "Read(/etc/shadow)" in settings["permissions"]["deny"]
    assert settings["theme"] == "dark"


def test_every_plugin_install_is_one_recorded_argv(tmp_path: Path) -> None:
    # The Runner seam again. Two things could be wrong here that only an argv assertion can
    # see: the marketplace must be registered *before* anything is installed from it (Fix
    # round 1, item 2 — a fresh machine cannot install a plugin from a marketplace it never
    # added), and the install call itself must carry none of the unmeasured `--scope`/`-y`
    # flags the first draft guessed (item 3).
    runner = FakeRunner()
    setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    preset = load_preset("recommended")
    claude = preset["plugins"]["claude"]
    assert ["claude", "plugin", "marketplace", "add", claude["source"]] in runner.calls
    for selector in preset["plugins"]["install"]:
        full = f"{selector}@{claude['marketplace']}"
        assert ["claude", "plugin", "install", full] in runner.calls
    # Codex has no verified marketplace for these two plugins (item 2): nothing is attempted.
    assert not any(argv and argv[0] == "codex" for argv in runner.calls)


def test_codex_gets_a_note_naming_the_unverified_plugins_rather_than_silence(
    tmp_path: Path,
) -> None:
    # Fix round 1 follow-up (R15's second clause, finished): a harness this preset cannot
    # install for on a verified path is a reported note, never silence and never a failure.
    # `agents = ["claude", "codex"]` is the preset's own default, so an ordinary run reaches
    # this for every machine that has Codex configured.
    preset = load_preset("recommended")
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=FakeRunner(),
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    expected = (
        f"codex: no verified marketplace for {', '.join(preset['plugins']['install'])}; "
        f"install manually if this harness supports it (see README)"
    )
    assert expected in report.notes


def test_a_harness_that_is_not_installed_is_a_note_not_a_failure(tmp_path: Path) -> None:
    # A missing `claude` binary must never turn a fresh-machine `setup` into a traceback — the
    # marketplace-add call is the first one this harness makes, and it is where a missing
    # binary would surface (`Runner` turns it into `Completed(127, ...)`).
    #
    # No mutation: this is `Runner`'s own fail-soft convention (a non-zero result is a note,
    # per `overlay.runner.Runner`'s own docstring), exercised here through the `FakeRunner`
    # script rather than guarding one line of this module's own whose removal would look like
    # a plausible bug — the "non-zero becomes a note" shape is `_install_plugins`' whole
    # structure, not a single guardable line.
    runner = FakeRunner(answers={"claude": Completed(127, "", "claude: command not found")})
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    assert any("claude" in note for note in report.notes)
    assert report.plugins_installed == ()


def test_the_overlay_offer_is_never_taken_without_being_asked(tmp_path: Path) -> None:
    # §6.1: `overlay create` runs `gh repo create` "after explicit confirmation". A default
    # that creates a GitHub repository is the one default this command may not have — and
    # `--yes`, which takes the detected defaults for everything else, must not take this one.
    #
    # Mutation: `setup`'s `if overlay is not None:` changed to `if True:` → reddens (the call
    # then reaches `_apply_overlay(None, ...)`, which is exactly the "taken without being
    # asked" shape this test exists to catch — `overlay=None` runs anyway).
    runner = FakeRunner()
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
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
    _seed_overlay(existing)
    machine = tmp_path / "config.toml"
    runner = FakeRunner()
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=machine,
        runner=runner,
        yes=True,
        overlay=str(existing),
        project_root=tmp_path / "project",
    )
    assert report.overlay == existing
    assert not any(argv[:2] == ["gh", "repo"] for argv in runner.calls)
    assert overlay_root(machine) == existing


def test_an_overlay_missing_the_layout_is_refused(tmp_path: Path) -> None:
    # Item 7: the overlay root is the machine's trust anchor, so an arbitrary directory that
    # merely happens to exist must not become one. `existing` here is empty — no
    # `.claude-plugin/plugin.json`, no `marketplace.json` — which is exactly the shape a
    # careless `--overlay /tmp/whatever` would have.
    #
    # Mutation: `_validate_overlay_root`'s `missing = [...]` line changed to `missing = []` →
    # reddens (an empty directory would then be accepted as an overlay root).
    empty = tmp_path / "not-an-overlay"
    empty.mkdir()
    with pytest.raises(Refusal, match="does not carry the overlay layout"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=FakeRunner(),
            yes=True,
            overlay=str(empty),
            project_root=tmp_path / "project",
        )


def test_an_overlay_inside_the_project_root_is_refused(tmp_path: Path) -> None:
    # Item 7, the other half and the one the coordinator's ruling calls the wave's actual
    # control: a path outside the repository that already carries a real overlay layout is not
    # something a hostile clone can create, but a path *inside* the repository is exactly the
    # shape of tree a clone can ship — so recording one there is refused regardless of how
    # convincing its layout is.
    #
    # Mutation: the `if candidate == resolved_project or resolved_project in candidate.parents:`
    # line changed to `if False:` → reddens (a nested overlay would then be recorded).
    project = tmp_path / "project"
    project.mkdir()
    nested = project / "vendored-overlay"
    nested.mkdir()
    _seed_overlay(nested)
    with pytest.raises(Refusal, match="is inside"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=FakeRunner(),
            yes=True,
            overlay=str(nested),
            project_root=project,
        )


def test_overlay_create_asks_github_and_records_the_new_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The first of §8.1's three answers: nothing exists yet, so `setup` both creates the
    # repository and records what it created — the same probe `overlay.create` uses
    # (`.claude-plugin`) is what tells this test the create branch, and not a no-op, ran.
    #
    # `home`, and not `Path.cwd()`, is asserted here rather than merely the leaf name: measured
    # while writing this module, `root=Path.cwd()` created a real `keelline-private/` inside
    # this checkout the first time this branch ran under a test, because `tmp_path` was never
    # in that call at all. Mutation: change `_apply_overlay`'s `root=home` back to
    # `root=Path.cwd()` → reddens on this line without touching the `.name` check alone.
    #
    # `monkeypatch.chdir(tmp_path)` is not decoration: it is what keeps that exact mutation's
    # own oracle run from recreating the real directory a second time — under the mutation,
    # the create call falls back to `Path.cwd()`, and this way that lands inside `tmp_path`
    # instead of wherever the process happened to be running from.
    monkeypatch.chdir(tmp_path)
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
        project_root=tmp_path / "project",
    )
    assert any(argv[:3] == ["gh", "repo", "create"] for argv in runner.calls)
    assert report.overlay == home / "keelline-private"
    assert overlay_root(machine) == report.overlay


def test_creating_an_overlay_without_yes_is_refused(tmp_path: Path) -> None:
    # Item 8, and the ruling's other half: creating a repository on GitHub is the one
    # irreversible, outward-facing act `setup` performs, and §6.1 asks for "explicit
    # confirmation" before it runs. Naming `create:<owner>/<name>` is not that confirmation by
    # itself — `--yes` is.
    #
    # Mutation: `_apply_overlay`'s `if not yes:` line changed to `if False:` → reddens (the
    # repository would then be created without `--yes`).
    runner = FakeRunner(on_call=_populate_overlay)
    with pytest.raises(Refusal, match="explicit confirmation"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=runner,
            yes=False,
            overlay="create:octo/keelline-private",
            project_root=tmp_path / "project",
        )
    assert not any(argv[:3] == ["gh", "repo", "create"] for argv in runner.calls)


def test_the_recorded_overlay_root_is_accepted_inside_and_refused_outside_by_attach(
    tmp_path: Path,
) -> None:
    # The C→D seam, asserted rather than assumed — and asserted through both halves, which is
    # what makes it the seam and not a guess: `setup --overlay <path>` records a root, and
    # `attach.read_binding` must accept a `--store` that is that root's own share for this
    # project and refuse, by the specific "own directory inside the overlay" guard, one that
    # is not. A bare `pytest.raises(Refusal)` with no message match could not tell that guard
    # apart from any other refusal `read_binding` might raise for an unrelated reason.
    #
    # No new mutations.toml entry: the guard both arms exercise is `binding.py`'s own
    # store-must-match-`permitted_roots` check, already load-bearing there under "the overlay
    # root comes from the machine file and not from the argument" (Wave C) — this test proves
    # the two ends of the seam agree, not a new line to mutate.
    existing = tmp_path / "overlay"
    existing.mkdir()
    _seed_overlay(existing)
    machine = tmp_path / "config.toml"
    setup(
        "recommended",
        home=tmp_path / "home",
        machine=machine,
        runner=FakeRunner(),
        yes=True,
        overlay=str(existing),
        project_root=tmp_path / "project",
    )
    project = _initialised_project(tmp_path)

    good_store = existing / "projects" / "widget" / "memory"
    binding = read_binding(project, store=good_store, machine=machine)
    assert binding.overlay == existing

    wrong_store = tmp_path / "elsewhere" / "memory"
    with pytest.raises(Refusal, match="own directory inside the overlay"):
        read_binding(project, store=wrong_store, machine=machine)


def test_a_second_run_is_idempotent(tmp_path: Path) -> None:
    # Two runs, one report each; the second installs no plugin twice and leaves the deny list
    # the same length.
    #
    # No mutation: idempotence here is an emergent property of guards this file already tests
    # on their own (the deny merge's `existing_deny`, and `write_machine`'s overlay-preserving
    # read-back from Task 12) run twice, not a separate line of its own.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    runner = FakeRunner()
    first = setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    second = setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    assert sorted(first.plugins_installed) == sorted(second.plugins_installed)
    settings = json.loads((home / USER_SETTINGS).read_text(encoding="utf-8"))
    preset = load_preset("recommended")
    assert len(settings["permissions"]["deny"]) == len(preset["deny"]["global"])


def test_a_second_run_does_not_reset_a_personal_value_the_owner_set(tmp_path: Path) -> None:
    # Fix round 1, item 1: the brief's own Task 13 step 1 asks for "[personal] from the
    # preset's [defaults.personal] overlaid by anything the caller passed" — a preset default
    # must never win over a value already recorded, whether that value came from the owner's
    # own hand or from an earlier `setup` run.
    #
    # Mutation: `_new_personal_values`'s `return {k: v for k, v in ... if k not in existing}`
    # changed to `return _personal_defaults(preset)` → reddens (the owner's "ru" is overwritten
    # back to the preset's own "").
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    runner = FakeRunner()
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    # The owner sets a personal value by hand between two runs.
    write_machine(machine, personal={"reply_language": "ru"}, overlay_root=None, machine={})
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    assert read_machine(machine)["personal"]["reply_language"] == "ru"


def test_a_malformed_overlay_spec_is_refused(tmp_path: Path) -> None:
    # `--overlay create:` with no slash, or a missing owner or name, is a typo — not a path to
    # try to interpret and not a repository to create somewhere unexpected.
    #
    # No mutation: this is ordinary input validation on a value only the operator types
    # (`owner, sep, name = spec.partition("/")`), not a trust-boundary guard something
    # downstream reads as permission — the guards the oracle curates for are the overlay-layout
    # and containment checks above, which this same branch also runs.
    with pytest.raises(Refusal):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=FakeRunner(),
            yes=True,
            overlay="create:no-slash-here",
            project_root=tmp_path / "project",
        )


def test_a_missing_keelline_on_path_is_a_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # D2: `uv tool install` has no `--from`, so the positional git URL form is what the note
    # must name; asserted here rather than left to eyeballing, since it is the one line a typo
    # in the URL or the tag would hide from every other test in this module.
    monkeypatch.setattr("shutil.which", lambda name: None)
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=FakeRunner(),
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    assert report.cli_on_path is False
    assert any(
        "uv tool install git+https://github.com/Nezhinskiy/keelline@v" in n for n in report.notes
    )
