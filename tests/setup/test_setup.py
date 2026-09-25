# tests/setup/test_setup.py
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from keelline import gitenv
from keelline.attach.api import read_binding
from keelline.errors import Failure, Refusal
from keelline.memory.api import overlay_root
from keelline.overlay.api import MARKETPLACE_MANIFEST, PLUGIN_MANIFEST
from keelline.presets import load_preset
from keelline.runner import Completed
from keelline.setup.api import USER_SETTINGS, setup
from keelline.setup.machine import read_machine, write_machine
from tests.gitfixture import git as _git

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
    mock's return value — the same shape `tests/overlay/test_create.py::FakeRunner` uses.

    This used to say it was not imported from there because the test tree was not importable
    and CONTRIBUTING forbade a cross-module import. No such rule exists, `tests/__init__.py` is
    tracked, and `tests/overlay/test_upgrade.py` imports that very class from that very module.
    The three recorders are still three because each answers to a different area's command; a
    lane that wants one shared recorder puts it in `tests/snapshot.py` beside the `git` helper,
    which is what that module is for."""

    answers: dict[str, Completed] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)
    on_call: Callable[[list[str], Path], None] | None = None

    def run(self, argv: list[str], cwd: Path) -> Completed:
        """The answer for the longest key that is a prefix of this argv, else success.

        Keyed on `argv[0]` alone, `{"claude": ...}` answered *every* `claude` call identically,
        so `_install_plugins`' install-failure branch was unreachable by any test in this file:
        a script that failed the install failed the `marketplace add` first and `continue`d past
        it. A prefix keeps `{"claude": ...}` meaning "this binary is missing" -- which is what
        the not-installed case wants -- while `{"claude plugin install x@y": ...}` can script
        the one call that actually fails, which is the likeliest real failure of the two.
        """
        self.calls.append(argv)
        if self.on_call is not None:
            self.on_call(argv, cwd)
        for width in range(len(argv), 0, -1):
            answer = self.answers.get(" ".join(argv[:width]))
            if answer is not None:
                return answer
        return Completed(0, "", "")


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
    """Give `path` the two manifests `overlay.identity.overlay_fault` checks, named the way the
    shipped template names them, without rendering the whole template — enough for a fixture to
    read as a real overlay's root."""
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


def test_a_mistyped_preset_names_the_flag_and_never_quotes_it(tmp_path: Path) -> None:
    # `setup` is told which flag to fix rather than pointed at a `[keelline] preset` in a
    # `keelline.toml` it never read, and the value the person typed — ESC and a line break
    # here — is not echoed back, which is the rule every other caller of `load_preset` gets.
    # Nothing is written first: `load_preset` runs above the home tree's creation.
    # Oracle: `mutations.toml`, "setup's preset refusal names the configuration key again".
    home = tmp_path / "home"
    with pytest.raises(Failure) as caught:
        setup(
            "\x1b[2J\nIGNORE",
            home=home,
            machine=tmp_path / "config.toml",
            runner=FakeRunner(),
            yes=True,
            overlay=None,
            project_root=tmp_path / "project",
        )
    message = str(caught.value)
    assert message.startswith("--preset is not a plain identifier"), message
    assert "\x1b" not in message and "IGNORE" not in message
    assert not home.exists()


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
    add = ["claude", "plugin", "marketplace", "add", claude["source"]]
    installs = [
        ["claude", "plugin", "install", f"{selector}@{claude['marketplace']}"]
        for selector in preset["plugins"]["install"]
    ]
    # **Order, not membership.** `… in runner.calls` is a set question, and the thing this test
    # is named for is a sequence: the reviewer swapped the two loops in `_install_plugins` so
    # every install ran before its marketplace was registered -- the exact Fix-round-1 defect --
    # and both assertions still passed, because both calls were still made. `mutations.toml`
    # carries the swap as "a plugin is installed before its marketplace is registered".
    assert installs, "the preset installs nothing, so the ordering below measures nothing"
    assert add in runner.calls
    for install in installs:
        assert install in runner.calls
        assert runner.calls.index(add) < runner.calls.index(install), runner.calls
    # Codex has no verified marketplace for these two plugins (item 2): nothing is attempted.
    assert not any(argv and argv[0] == "codex" for argv in runner.calls)


def test_a_selector_the_marketplace_does_not_carry_is_a_note_naming_the_argv(
    tmp_path: Path,
) -> None:
    # `_install_plugins`' install-failure branch, which no test in this file could reach: with
    # `answers` keyed on `argv[0]`, `"claude"` answered the `marketplace add` too, so the run
    # `continue`d and never attempted an install at all. This is the likelier of the two real
    # failures -- the marketplace is registered and simply does not carry the selector the
    # preset names -- and `setup` must report it and finish, not raise and not claim it
    # installed.
    #
    # Mutation: `_install_plugins`' `notes.append(f"{agent}: `{' '.join(argv)}` did not
    # succeed ({detail})")` replaced by `pass` -> reddens on the missing note, while
    # `plugins_installed` stays empty, which is what makes the two assertions different
    # questions rather than one asked twice.
    preset = load_preset("recommended")
    claude = preset["plugins"]["claude"]
    selector = preset["plugins"]["install"][0]
    full = f"{selector}@{claude['marketplace']}"
    runner = FakeRunner(
        answers={
            f"claude plugin install {full}": Completed(1, "", f"no plugin named {selector} here")
        }
    )
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    assert ["claude", "plugin", "marketplace", "add", claude["source"]] in runner.calls
    assert ["claude", "plugin", "install", full] in runner.calls
    assert selector not in report.plugins_installed
    # The other selector still installs: one failure is one note, never an abandoned run.
    assert preset["plugins"]["install"][1] in report.plugins_installed
    assert any(f"claude plugin install {full}" in note for note in report.notes), report.notes
    assert any("no plugin named" in note for note in report.notes), report.notes


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
    # per `keelline.runner.Runner`'s own docstring), exercised here through the `FakeRunner`
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
    # `--yes`, which confirms creating one, must not stand in for naming one.
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
    # Mutation (`mutations.toml`, "the overlay probe stops looking for the manifests at all"):
    # `overlay.identity.overlay_fault` stops iterating the manifests → an empty directory is
    # accepted as an overlay root and this reddens.
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
    # Mutation (`mutations.toml`, "setup stops refusing an overlay root inside the project"):
    # `_outside_the_project`'s path condition becomes `if False:` → a nested overlay is recorded
    # and this reddens.
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


# --- everything structural, above the first write (review findings 2, 3, 13 and 22) ---


def _wrote_anything(home: Path, machine: Path) -> list[str]:
    """What a run left behind on this machine: the two files `setup` writes, by name.

    A list rather than a boolean so a failing assertion says *which* file survived a refusal,
    and asserted non-empty by a companion test below — a check that a refused run wrote nothing
    proves nothing unless the same fixture, unrefused, writes something.
    """
    return [str(path) for path in (machine, home / USER_SETTINGS) if path.is_file()]


def test_a_refused_overlay_path_is_refused_before_the_first_write(tmp_path: Path) -> None:
    # Finding 3. `--overlay /typo` used to be validated at the very bottom of `setup`: a stub
    # runner recorded the marketplace add and both plugin installs, the machine file and
    # `~/.claude/settings.json` were both on disk, and only then did `Refusal: /typo is not a
    # directory` propagate — with the `SetupReport` discarded, so the caller saw only the
    # refusal and never a word about what had already happened. A purely structural check on a
    # caller-supplied path belongs above the first write.
    #
    # Mutation (`mutations.toml`, "setup asks whether --overlay is an overlay after it has
    # already written"): the hoisted `_requested_overlay` call is replaced by one that trusts
    # the path, leaving only `_apply_overlay`'s floor → the refusal still arrives, and this
    # reddens on the two files and the argv.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    runner = FakeRunner()
    with pytest.raises(Refusal, match="is not a directory"):
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=True,
            overlay=str(tmp_path / "typo"),
            project_root=tmp_path / "project",
        )
    assert _wrote_anything(home, machine) == []
    assert runner.calls == [], "no plugin was installed for a run that refuses its own arguments"


def test_the_same_fixture_without_the_typo_writes_both_files(tmp_path: Path) -> None:
    # The non-vacuity guard under the test above: the assertions there are about a *refused*
    # run, and they would pass just as well if `setup` wrote nothing under any circumstances.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    existing = tmp_path / "overlay"
    existing.mkdir()
    _seed_overlay(existing)
    runner = FakeRunner()
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=str(existing),
        project_root=tmp_path / "project",
    )
    assert _wrote_anything(home, machine) == [str(machine), str(home / USER_SETTINGS)]
    assert runner.calls != []


def test_a_created_overlay_is_refused_before_the_repository_exists(tmp_path: Path) -> None:
    # Finding 2, the most serious of the eleven: the documented command run from `$HOME` —
    # `--root` defaulting to `.` — created the private repository on GitHub, cloned it, renamed
    # both manifests and installed the secret scan, and *then* refused, because `home/<name>`
    # lies inside the "project root" that `--root` had defaulted to. The machine file was left
    # with no `[overlay]` table and nothing told the owner the repository now existed.
    # `home/<name>` needs no created tree: it is `overlay.api.target_root`'s answer, known from
    # the arguments alone.
    #
    # Mutation ("setup computes where a created overlay lands only after creating it"): the
    # `_outside_the_project(destination, ...)` call in `_requested_overlay` is dropped, leaving
    # `_apply_overlay`'s floor → `gh repo create` runs, and this reddens on the argv assertion.
    home = tmp_path / "home"
    home.mkdir()
    machine = tmp_path / "config.toml"
    runner = FakeRunner(on_call=_populate_overlay)
    with pytest.raises(Refusal, match="is inside"):
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=True,
            overlay="create:octo/keelline-private",
            project_root=home,
        )
    assert not any(argv[:3] == ["gh", "repo", "create"] for argv in runner.calls)
    assert not (home / "keelline-private").exists()
    assert _wrote_anything(home, machine) == []


def test_a_directory_whose_manifests_name_another_plugin_is_not_an_overlay(tmp_path: Path) -> None:
    # Finding 22, first half. The probe was the two manifest *files* existing, which the
    # Keelline checkout itself satisfies and any Claude Code plugin repository satisfies — so
    # "carries the overlay's own layout" excluded almost nothing. The manifests are now read,
    # and have to name the tree `keelline-overlay[-<owner>]`.
    #
    # Mutation ("the overlay probe stops reading what the manifests name"): `identity`'s
    # `_claims` arm is dropped → this directory is accepted and the refusal never fires.
    impostor = tmp_path / "some-plugin"
    (impostor / ".claude-plugin").mkdir(parents=True)
    (impostor / PLUGIN_MANIFEST).write_text(
        json.dumps({"name": "somebody-elses-plugin"}), encoding="utf-8"
    )
    (impostor / MARKETPLACE_MANIFEST).write_text(
        json.dumps({"name": "somebody-elses-marketplace", "plugins": []}), encoding="utf-8"
    )
    with pytest.raises(Refusal, match="does not name a Keelline overlay"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=FakeRunner(),
            yes=True,
            overlay=str(impostor),
            project_root=tmp_path / "project",
        )


def test_an_overlay_that_holds_the_project_root_is_refused(tmp_path: Path) -> None:
    # Finding 22, second half. The containment refused `candidate == project` or `project in
    # candidate.parents` and nothing else, so a *parent* passed — and `git worktree add
    # .worktrees/x`, which this project's own `worktree-by-default` preset rule makes the
    # ordinary case, puts `--root` exactly there. A clone shipping its two manifests at its own
    # root was then accepted as the machine's trust anchor.
    #
    # Mutation ("setup stops refusing an overlay root that holds the project"): the
    # `or resolved_candidate in resolved_project.parents` arm becomes `or False` → the clone's
    # own root is recorded and this reddens.
    clone = tmp_path / "clone"
    clone.mkdir()
    _seed_overlay(clone)
    worktree = clone / ".worktrees" / "wave-1"
    worktree.mkdir(parents=True)
    with pytest.raises(Refusal, match="holds it, or is it"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=FakeRunner(),
            yes=True,
            overlay=str(clone),
            project_root=worktree,
        )


def test_a_sibling_checkout_of_the_project_is_never_the_trust_anchor(tmp_path: Path) -> None:
    # Finding 22, the case no path comparison can see: `git worktree add ../side` is git's own
    # documented layout and this repository's own convention, and a worktree beside the checkout
    # is neither inside it nor above it. The clone's manifests sit in the *other* checkout of
    # the same repository, so both path arms passed and the tree a clone ships was recorded.
    # `git worktree list`, asked from the project, is what tells two checkouts of one repository
    # apart from two repositories.
    #
    # No mutation reddens this alone: the project's listing and the candidate-side walk both
    # refuse it. Each is proven by a test only it catches — the bare-shaped directory that
    # claims to be a checkout, and the separate-git-dir checkout.
    clone = tmp_path / "clone"
    clone.mkdir()
    _git(clone, "init", "-q", "-b", "main")
    _seed_overlay(clone)
    (clone / "README.md").write_text("x", encoding="utf-8")
    _git(clone, "add", "-A")
    _git(clone, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "init")
    worktree = tmp_path / "clone.worktrees" / "wave-1"
    _git(clone, "worktree", "add", "-q", str(worktree), "-b", "wave-1")
    assert clone.resolve() not in worktree.resolve().parents, "beside the checkout, not under it"
    with pytest.raises(Refusal, match="same repository"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=FakeRunner(),
            yes=True,
            overlay=str(clone),
            project_root=worktree,
        )


def test_an_overlay_outside_every_checkout_is_still_recorded(tmp_path: Path) -> None:
    # The other side of the two tests above, and the reason they are not simply "refuse
    # everything": a real overlay is a repository of its own, beside the project and unrelated
    # to it, and `git` answering for both must not make them the same tree.
    project = tmp_path / "project"
    project.mkdir()
    _git(project, "init", "-q", "-b", "main")
    overlay = tmp_path / "keelline-private"
    overlay.mkdir()
    _git(overlay, "init", "-q", "-b", "main")
    _seed_overlay(overlay)
    machine = tmp_path / "config.toml"
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=machine,
        runner=FakeRunner(),
        yes=True,
        overlay=str(overlay),
        project_root=project,
    )
    assert report.overlay == overlay
    assert overlay_root(machine) == overlay


def _commit_a_bare_shaped_directory(checkout: Path) -> Path:
    """Commit `ov/` into `checkout`, shaped like a bare repository and carrying the overlay's
    two manifests; `ov/`.

    `HEAD`, `objects/` and `refs/` are three paths any repository can commit, and `git`'s
    discovery reads a directory holding all three as a bare repository of its own when
    `safe.bareRepository` is unset. With the manifests beside them, `ov/` in every checkout is a
    tree the clone shipped and that reads as an overlay.
    """
    shaped = checkout / "ov"
    (shaped / "objects").mkdir(parents=True)
    (shaped / "refs").mkdir()
    (shaped / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (shaped / "objects" / ".keep").write_text("", encoding="utf-8")
    (shaped / "refs" / ".keep").write_text("", encoding="utf-8")
    _seed_overlay(shaped)
    _git(checkout, "add", "-A")
    _git(checkout, "commit", "-qm", "init")
    return shaped


def _clone_with_a_bare_shaped_directory(tmp_path: Path) -> tuple[Path, Path]:
    """A project repository that commits a bare-shaped `ov/`, plus two sibling worktrees of it;
    `(main checkout, the worktrees' shared parent)`."""
    project = tmp_path / "proj"
    project.mkdir()
    _git(project, "init", "-q", "-b", "main")
    _commit_a_bare_shaped_directory(project)
    worktrees = tmp_path / "proj.wt"
    _git(project, "worktree", "add", "-q", str(worktrees / "wave-1"), "-b", "wave-1")
    _git(project, "worktree", "add", "-q", str(worktrees / "wave-2"), "-b", "wave-2")
    return project, worktrees


# `safe.bareRepository` arrived in git 2.38, and an older git ignores a `-c` key it does not
# know. "ignores-safe-bare" stands that git in by emptying the pair, so the refusals that must not
# depend on it are proven on the git CI has.
GITS = ["current", "ignores-safe-bare"]


def _as(git_version: str, monkeypatch: pytest.MonkeyPatch) -> None:
    if git_version == "ignores-safe-bare":
        monkeypatch.setattr("keelline.setup.run._EXPLICIT_BARE", ())


def _record(tmp_path: Path, overlay: Path, project_root: Path) -> None:
    setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=FakeRunner(),
        yes=True,
        overlay=str(overlay),
        project_root=project_root,
    )


@pytest.mark.parametrize("git_version", GITS)
@pytest.mark.parametrize("root", ["proj", "proj.wt/wave-2", "proj.wt/wave-2/no/such/dir"])
def test_a_bare_shaped_directory_in_a_sibling_checkout_is_never_the_trust_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, root: str, git_version: str
) -> None:
    # The sibling-checkout arm asked `git rev-parse --git-common-dir` *from inside the
    # candidate*, and git answered for the committed `ov/` rather than for the checkout it sits
    # in: `proj.wt/wave-1/ov` reported itself as its own common directory, so it was "not the
    # same repository" and was recorded — while `proj.wt/wave-1` itself was refused. The
    # checkouts are now listed from the project's side, which the candidate's bytes cannot reach.
    #
    # The listing and the candidate-side arm each refuse this layout, so breaking either one
    # leaves it refused: the test below proves the listing alone, and the separate-git-dir test
    # the candidate side alone. A `--root` that does not exist is asked about from its nearest
    # directory that does, where it used to be asked from its parent and nothing else.
    #
    # Mutation ("setup asks git about --root from a directory that does not exist"): the walk
    # up becomes one step → `no/such` does not exist, git gives no answer, only the path arm
    # stands and the third root reddens.
    _as(git_version, monkeypatch)
    _clone_with_a_bare_shaped_directory(tmp_path)
    with pytest.raises(Refusal, match="same repository"):
        _record(tmp_path, tmp_path / "proj.wt" / "wave-1" / "ov", tmp_path / root)
    assert not (tmp_path / "config.toml").exists(), "refused above the first write"


@pytest.mark.parametrize("git_version", GITS)
def test_a_bare_shaped_directory_that_claims_to_be_a_checkout_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_version: str
) -> None:
    # Why the listing stays the arm that decides, and the candidate side only adds to it. A
    # committed `ov/config` saying `core.bare = false` makes a git that ignores
    # `safe.bareRepository` answer from inside `ov/` with `ov/` as a repository that is *not*
    # bare, so the candidate-side walk stops there and finds another repository. The project's
    # own listing of its checkouts is not something the candidate's bytes can reach.
    #
    # Mutation ("setup stops asking git whether the overlay is a checkout of the project"): the
    # per-checkout comparison becomes `if False:` → the `ignores-safe-bare` case is recorded.
    _as(git_version, monkeypatch)
    project = tmp_path / "proj"
    project.mkdir()
    _git(project, "init", "-q", "-b", "main")
    (project / "ov").mkdir()
    (project / "ov" / "config").write_text("[core]\n\tbare = false\n", encoding="utf-8")
    _commit_a_bare_shaped_directory(project)
    linked = tmp_path / "proj.wt" / "wave-1"
    _git(project, "worktree", "add", "-q", str(linked), "-b", "wave-1")
    with pytest.raises(Refusal, match="same repository"):
        _record(tmp_path, linked / "ov", project)


@pytest.mark.parametrize("git_version", GITS)
def test_a_root_inside_a_bare_shaped_directory_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_version: str
) -> None:
    # The same shape from the project's side: run from `proj/ov`, git's own discovery stops at
    # `ov/` and names *it* as the repository, whose only "checkout" is itself — so the sibling
    # `proj.wt/wave-1/ov` lies outside every listed checkout and every path arm. git's answer
    # says the repository is bare, and on every git version that is what refuses: a project
    # root with no checkout of its own to compare against is not one.
    #
    # Mutation ("setup stops refusing a root git reads as a bare repository"): the
    # `--is-bare-repository` refusal becomes `if False:` → the current-git case falls to the
    # retry's refusal, which does not say "bare repository", and the other case is recorded.
    _as(git_version, monkeypatch)
    project, _ = _clone_with_a_bare_shaped_directory(tmp_path)
    with pytest.raises(Refusal, match="bare repository"):
        _record(tmp_path, tmp_path / "proj.wt" / "wave-1" / "ov", project / "ov")
    assert not (tmp_path / "config.toml").exists(), "refused above the first write"


@pytest.mark.parametrize("git_version", GITS)
def test_a_checkout_the_listing_names_by_its_git_directory_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_version: str
) -> None:
    # `git worktree list` does not name every checkout. With `--separate-git-dir` the main
    # worktree is listed as the git directory (`sep.git`), which does not record where its work
    # tree is, so from the linked worktree `s.wt/w` the main checkout `s` is on no list and its
    # `ov/` passed every listed arm. The candidate-side arm walks up from the candidate to the
    # first repository git answers for that is not bare — `s`, through its `.git` file — and
    # refuses when that is the project's. It can only add a refusal: whatever the candidate's
    # bytes make git answer, the listing's refusals still stand.
    #
    # Mutation ("setup stops asking git from the candidate's side"): the candidate-side
    # refusal becomes `if False:` → `s/ov` is recorded and both cases redden.
    # Mutation ("the candidate-side walk stops at the first directory git will not answer
    # for"): the step to the parent becomes `return None` → git refuses `ov/` as a bare
    # repository, the walk never reaches `s`, and the current-git case reddens.
    # Mutation ("the candidate-side walk takes a bare repository's answer as the candidate's"):
    # the `== "false"` test becomes `!= "?"` → on a git that ignores the key, `ov/` answers for
    # itself as a bare repository, the walk stops there, and the other case reddens.
    _as(git_version, monkeypatch)
    main, sep = tmp_path / "s", tmp_path / "sep.git"
    _git(tmp_path, "init", "-q", "-b", "main", "--separate-git-dir", str(sep), str(main))
    _commit_a_bare_shaped_directory(main)
    linked = tmp_path / "s.wt" / "w"
    _git(main, "worktree", "add", "-q", str(linked), "-b", "w")
    with pytest.raises(Refusal, match="same repository"):
        _record(tmp_path, main / "ov", linked)


@pytest.mark.parametrize("git_version", GITS)
def test_a_submodule_checkout_is_refused_from_a_worktree_of_the_submodule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_version: str
) -> None:
    # The second layout the listing names by its git directory: a submodule's own checkout is
    # listed as `sup/.git/modules/sub`, so from a linked worktree of the submodule `sup/sub` is
    # on no list. The candidate-side walk reaches it through `sup/sub/.git`.
    #
    # Mutation ("setup stops asking git from the candidate's side"): as above, both cases.
    _as(git_version, monkeypatch)
    sub = tmp_path / "sub"
    sub.mkdir()
    _git(sub, "init", "-q", "-b", "main")
    _commit_a_bare_shaped_directory(sub)
    sup = tmp_path / "sup"
    sup.mkdir()
    _git(sup, "init", "-q", "-b", "main")
    _git(sup, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "sub")
    _git(sup, "commit", "-qm", "add the submodule")
    linked = tmp_path / "sup.wt"
    _git(sup / "sub", "worktree", "add", "-q", str(linked), "-b", "w")
    with pytest.raises(Refusal, match="same repository"):
        _record(tmp_path, sup / "sub" / "ov", linked)


def test_a_sibling_checkout_spelled_in_another_case_is_still_refused(tmp_path: Path) -> None:
    # On a volume that folds case — macOS's default — `PROJ.WT/wave-1/ov` is the sibling
    # checkout's `ov/`, and `Path.resolve()` keeps the case it was given, so a string comparison
    # against the listed `proj.wt/wave-1` said "outside". Directories are now compared as the
    # filesystem sees them.
    #
    # No mutation entry: the oracle runs on Linux, where this layout cannot exist and the test
    # skips, so an entry would be reported as proving nothing. `_overlaps`' own arms are pinned
    # by the entries on the inside and holds tests.
    project, _ = _clone_with_a_bare_shaped_directory(tmp_path)
    candidate = tmp_path / "PROJ.WT" / "wave-1" / "ov"
    if not candidate.is_dir():
        pytest.skip("this filesystem is case-sensitive")
    with pytest.raises(Refusal, match="same repository"):
        _record(tmp_path, candidate, project)


# Stands for "git printed bytes the locale cannot decode": `git_run` raises rather than answer.
UNDECODABLE = (-2, "undecodable")

FAILURES: dict[str, Callable[[tuple[str, ...]], tuple[int, str] | None]] = {
    # What the listing call answers.
    "listing-exit": lambda args: (128, "") if "worktree" in args else None,
    "listing-empty": lambda args: (0, "") if "worktree" in args else None,
    "listing-undecodable": lambda args: UNDECODABLE if "worktree" in args else None,
    # What the project-side `rev-parse` answers.
    "common-undecodable": lambda args: UNDECODABLE if "rev-parse" in args else None,
    "answers-only-without-the-key": (
        lambda args: (128, "") if "rev-parse" in args and "-c" in args else None
    ),
}


@pytest.mark.parametrize("failure", sorted(FAILURES))
def test_checkouts_git_cannot_list_refuse_the_overlay_rather_than_pass_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    # Once git has said the project is a repository, "no answer" about its checkouts is not
    # "none of them holds the candidate". It used to be: a `git` that gave no answer for the
    # candidate returned `None`, `None` differed from the project's common directory, and the
    # candidate was recorded. And `gitenv.git_run` decodes with `text=True`, so a path git
    # prints in bytes that are not the locale's encoding raised `UnicodeDecodeError` out of
    # `setup` as an internal error.
    #
    # Mutation ("setup stops refusing an overlay when git cannot list the project's
    # checkouts"): the listing's refusal becomes `return _Repository(common, [])` → the
    # legitimate-looking overlay below is recorded and `listing-exit` and `listing-empty`
    # redden.
    # Mutation ("setup stops refusing an overlay when git answers in undecodable bytes"): the
    # `except UnicodeDecodeError` arm becomes `except LookupError` → the error escapes instead
    # of a `Refusal` and the two `-undecodable` cases redden.
    # Mutation ("setup takes an answer git gave only without the key"): the refusal after the
    # retry becomes `pass` → `answers-only-without-the-key` is recorded and reddens.
    project = tmp_path / "project"
    project.mkdir()
    _git(project, "init", "-q", "-b", "main")
    overlay = tmp_path / "keelline-private"
    overlay.mkdir()
    _git(overlay, "init", "-q", "-b", "main")
    _seed_overlay(overlay)
    real = gitenv.git_run

    def failing(root: Path, *args: str, **kwargs: Any) -> tuple[int, str]:
        answer = FAILURES[failure](args)
        if answer is None:
            return real(root, *args, **kwargs)
        if answer == UNDECODABLE:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        return answer

    monkeypatch.setattr("keelline.setup.run.git_run", failing)
    with pytest.raises(Refusal, match="could not list"):
        _record(tmp_path, overlay, project)


@pytest.mark.parametrize("git_version", GITS)
def test_an_overlay_beside_a_project_with_worktrees_is_still_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_version: str
) -> None:
    # The legitimate user the tests above must not lose: a project with a main checkout and a
    # sibling worktree, as this project's own preset lays it out, and an overlay that is a
    # repository of its own beside both. Its root is under no checkout and holds none, and git
    # asked from inside it answers with its own repository, so it is recorded — from either
    # checkout, and on either git.
    _as(git_version, monkeypatch)
    project, worktrees = _clone_with_a_bare_shaped_directory(tmp_path)
    overlay = tmp_path / "keelline-private"
    overlay.mkdir()
    _git(overlay, "init", "-q", "-b", "main")
    _seed_overlay(overlay)
    for root in (project, worktrees / "wave-1"):
        machine = tmp_path / f"{root.name}.toml"
        report = setup(
            "recommended",
            home=tmp_path / "home",
            machine=machine,
            runner=FakeRunner(),
            yes=True,
            overlay=str(overlay),
            project_root=root,
        )
        assert report.overlay == overlay
        assert overlay_root(machine) == overlay


def test_a_symlinked_claude_directory_is_a_refusal_that_names_the_link(tmp_path: Path) -> None:
    # Finding 13. `fsops.write_within` walks `.claude` with `O_NOFOLLOW`, so a home managed by
    # stow, chezmoi or a synced directory raised `UnsafePath` — which `cli.run`'s final handler
    # renders as `keelline: internal error: UnsafePath: …`, exit 2, for the most common
    # non-default home layout there is, and only *after* the machine file had been written. The
    # containment rule has two stages and this lane had only the second; `config.paths.contained`
    # is the first, and it now runs above the first write and names the link and the way out.
    #
    # Mutation ("setup meets a symlinked ~/.claude only at write time"): the
    # `_check_settings_path(home)` call is dropped → the write-time floor still refuses, so the
    # refusal survives; this reddens on the machine file and on the remedy the message carries.
    home = tmp_path / "home"
    home.mkdir()
    real = tmp_path / "dotfiles" / ".claude"
    real.mkdir(parents=True)
    (home / ".claude").symlink_to(real)
    machine = tmp_path / "config.toml"
    with pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=FakeRunner(),
            yes=True,
            overlay=None,
            project_root=tmp_path / "project",
        )
    message = str(refused.value)
    assert str(home / ".claude") in message and str(real) in message
    assert f"--home {real.parent}" in message, "the refusal has to carry a command that works"
    assert not machine.is_file(), "the machine file was written before the refusal"


def test_a_claude_directory_that_becomes_a_symlink_after_the_check_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The floor under the test above, and not dead: a component that becomes a symlink between
    # the check and the write can only be refused by the `O_NOFOLLOW` walk, and that interval is
    # the whole reason the walk exists. Patching the first stage out is how the interval is
    # reached deterministically — the alternative is a race nothing can schedule.
    #
    # Mutation ("the write-time containment on the settings file is swallowed"): the
    # `except UnsafePath` arm stops raising → `setup` reports a settings file it never wrote.
    monkeypatch.setattr("keelline.setup.run._check_settings_path", lambda home: None)
    home = tmp_path / "home"
    home.mkdir()
    real = tmp_path / "elsewhere" / ".claude"
    real.mkdir(parents=True)
    (home / ".claude").symlink_to(real)
    with pytest.raises(Refusal, match="never follows a symlink"):
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "config.toml",
            runner=FakeRunner(),
            yes=True,
            overlay=None,
            project_root=tmp_path / "project",
        )


def test_the_plugin_config_mirror_follows_the_machine_file(tmp_path: Path) -> None:
    # Finding 21. The mirror was written from `_new_personal_values`, which is empty on every
    # run after the first — so an owner who set `reply_language` in the machine file, the
    # documented way (`README.md`: "Written by: you, or `keelline setup`"), kept `""` in
    # `~/.claude/settings.json` for ever, and Claude Code read that. The mirror is a projection
    # of the machine file and is recomputed from it on every run. The direction is a decision,
    # recorded in `setup.run`: a value set in Claude Code's own plugin-config UI loses to the
    # machine file, because one file has to win and that one is the file every reader reads.
    #
    # Mutation ("setup mirrors only the values this run itself added"): the argument goes back
    # to `personal` → the second run leaves `""` in the settings file and this reddens.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    for _ in range(1):
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=FakeRunner(),
            yes=True,
            overlay=None,
            project_root=tmp_path / "project",
        )
    write_machine(machine, personal={"reply_language": "ru"}, overlay_root=None, machine={})
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=FakeRunner(),
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    settings = json.loads((home / USER_SETTINGS).read_text(encoding="utf-8"))
    options = settings["pluginConfigs"]["keelline@keelline-marketplace"]["options"]
    assert options["reply_language"] == "ru"
    assert options["artifact_language"] == "en", "a value nobody changed still round-trips"


def test_a_created_tree_that_is_not_an_overlay_says_the_repository_now_exists(
    tmp_path: Path,
) -> None:
    # The one refusal that cannot precede a write, and what it owes the owner. `--overlay
    # create:` asks GitHub to generate from a template repository this project does not publish,
    # so what arrives is whatever is on that account — and if it is not an overlay, the run has
    # to say so *and* say that a private repository now exists, because the `SetupReport` is
    # discarded on a refusal and nothing else would ever tell them.
    def _wrong_tree(argv: list[str], cwd: Path) -> None:
        if argv[:3] != ["gh", "repo", "create"]:
            return
        target = cwd / argv[3].split("/")[-1] / ".claude-plugin"
        target.mkdir(parents=True, exist_ok=True)
        for name, body in (
            ("plugin.json", {"name": "not-an-overlay"}),
            ("marketplace.json", {"name": "not-a-marketplace", "plugins": []}),
        ):
            (target / name).write_text(json.dumps(body), encoding="utf-8")

    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "config.toml",
            runner=FakeRunner(on_call=_wrong_tree),
            yes=True,
            overlay="create:octo/keelline-private",
            project_root=tmp_path / "project",
        )
    message = str(refused.value)
    assert "does not name a Keelline overlay" in message
    assert "octo/keelline-private was created and cloned" in message
    assert "nothing was recorded in the machine configuration" in message
    assert overlay_root(tmp_path / "config.toml") is None


@pytest.mark.parametrize("per_file", [False, True])
def test_the_home_a_symlinked_settings_file_suggests_is_one_that_works(
    tmp_path: Path, per_file: bool
) -> None:
    # The remedy is only worth printing if following it does what it says. `stow` folds a package
    # as far as it can, so with `~/.claude` already created by Claude Code it links the *file* and
    # not the directory — and the first draft's arm compared the link's basename to its target's,
    # which is trivially true for a per-file link. It printed `--home <dotfiles>/claude`, under
    # which this command writes `<dotfiles>/claude/.claude/settings.json`, exits 0, and leaves the
    # file the link leads to untouched: finding 14's shape arriving through the remedy. So the
    # test follows the advice rather than matching a string, in both shapes of the accident.
    #
    # Mutation (`mutations.toml`, "the symlink remedy prints a --home that writes somewhere
    # else"): `_home_that_leads_there` stops checking that the link leads to a
    # `.claude/settings.json` at all → the per-file case below gets a command, and the
    # companion test's "no --home can name it" never fires.
    home = tmp_path / "home"
    home.mkdir()
    leads_to = tmp_path / "dotfiles" / ".claude" / "settings.json"
    leads_to.parent.mkdir(parents=True)
    if per_file:
        leads_to.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        (home / ".claude").mkdir()
        (home / USER_SETTINGS).symlink_to(leads_to)
    else:
        (home / ".claude").symlink_to(leads_to.parent)
    with pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "config.toml",
            runner=FakeRunner(),
            yes=True,
            overlay=None,
            project_root=tmp_path / "project",
        )
    advised = str(refused.value).partition("--home ")[2].partition("`")[0]
    assert advised, "the refusal printed no command at all"
    setup(
        "recommended",
        home=Path(advised),
        machine=tmp_path / "second.toml",
        runner=FakeRunner(),
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    # The advised run wrote the file the link leads to, and not a second one beside it.
    assert "permissions" in json.loads(leads_to.read_text(encoding="utf-8"))
    assert not (Path(advised) / USER_SETTINGS).is_symlink()
    assert (Path(advised) / USER_SETTINGS).resolve() == leads_to.resolve()


def test_a_home_layout_no_home_can_express_says_so_rather_than_printing_a_command(
    tmp_path: Path,
) -> None:
    # What `stow` actually produces for a package named `claude`:
    # `~/.claude/settings.json -> <dotfiles>/claude/settings.json`. `--home H` writes
    # `H/.claude/settings.json` and nothing else, so no value of `H` names that target — and an
    # honest "this layout cannot be expressed, here are the two ways out" beats a command that
    # silently writes somewhere no reader reads.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    leads_to = tmp_path / "dotfiles" / "claude" / "settings.json"
    leads_to.parent.mkdir(parents=True)
    leads_to.write_text("{}\n", encoding="utf-8")
    (home / USER_SETTINGS).symlink_to(leads_to)
    with pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "config.toml",
            runner=FakeRunner(),
            yes=True,
            overlay=None,
            project_root=tmp_path / "project",
        )
    message = str(refused.value)
    assert "no --home can name it" in message
    assert "keelline setup --home" not in message, "a command that cannot work is worse than none"
    assert "adopt it" in message, "the way out has to be named, not just the refusal"


def test_a_per_file_settings_link_is_written_through_settings_and_not_under_home(
    tmp_path: Path,
) -> None:
    # R3: `stow` links `~/.claude/settings.json` itself into a dotfiles tree, and no `--home`
    # value writes that file — `--home <dotfiles>/claude` writes `<dotfiles>/claude/.claude/
    # settings.json`. `--settings PATH` names the file. The link under `home` is left exactly
    # as it was; the dotfiles file gains the deny rules; nothing new appears under `home`.
    #
    # Mutation (declared): the `root, relative = …` line -> `(home, USER_SETTINGS)`
    # unconditionally. What it actually does is recorded beside the assertion below.
    home = tmp_path / "home"
    dotfiles = tmp_path / "dotfiles" / "claude"
    dotfiles.mkdir(parents=True)
    real = dotfiles / "settings.json"
    real.write_text("{}\n", encoding="utf-8")
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").symlink_to(real)
    before = sorted(str(p.relative_to(home)) for p in home.rglob("*"))
    setup(
        "recommended",
        home=home,
        machine=tmp_path / "machine.toml",
        runner=FakeRunner(),
        yes=False,
        overlay=None,
        project_root=tmp_path / "project",
        settings=real,
    )
    written = json.loads(real.read_text(encoding="utf-8"))
    # Read defensively so the failure says which file was written rather than raising a
    # `KeyError` on a document the deny rules never reached: under the declared mutation the
    # write lands under `home` — replacing the link with a real file of the same name, so the
    # inventory below is unchanged — and the dotfiles file is still the empty `{}` it started
    # as. That silence is the whole defect, and this sentence is what names it.
    deny = written.get("permissions", {}).get("deny", [])
    assert "Read(.env*)" in deny, f"the file --settings named was not written: {written}"
    assert sorted(str(p.relative_to(home)) for p in home.rglob("*")) == before


def test_a_settings_path_whose_directory_is_not_there_is_refused_before_anything_is_written(
    tmp_path: Path,
) -> None:
    # The structural question `setup`'s own docstring promises is asked "while nothing is on
    # disk", asked for the spelling that skipped it. `_check_settings_path(home)` ran only when
    # `settings is None`, so with `--settings` the refusal came from `_write_user_settings` —
    # after `home.mkdir(parents=True)` and after `write_machine`. A typo in the directory
    # component therefore created the home tree, wrote the machine configuration, and exited 2,
    # and the two cases below asserted the refusal and its sentence while never asking that.
    #
    # Mutation (declared, "setup asks about the --settings directory only at write time"): the
    # `else:` arm becomes `pass`. The `Refusal` still comes — one frame later — so the two
    # `exists()` assertions are what redden, and the `raises` is not the claim here.
    home = tmp_path / "home"
    machine = tmp_path / "machine.toml"
    missing = tmp_path / "not-there" / "settings.json"
    with pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=FakeRunner(),
            yes=False,
            overlay=None,
            project_root=tmp_path / "project",
            settings=missing,
        )
    assert str(missing) in str(refused.value)
    assert "has to exist and be a real directory" in str(refused.value)
    assert not home.exists(), sorted(p.name for p in home.rglob("*"))
    assert not machine.exists()


def test_a_settings_path_whose_directory_is_not_there_is_a_refusal_and_not_an_internal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fix round 1, item 2. `_write_user_settings` caught only `UnsafePath`, and `write_within`
    # opens the root itself before the loop that wraps `ELOOP`/`ENOTDIR` into one — so a root
    # that is not there raises a bare `FileNotFoundError`, which left the library and reached
    # `cli.run`'s final handler as `keelline: internal error`, exit 2, no remedy. A typo in
    # `--settings`' directory component is the ordinary way to get there.
    #
    # This is now the FLOOR under the case above rather than the case itself:
    # `_check_settings_parent` refuses the same two conditions one stage earlier, so the
    # interval in which the directory goes away between the check and the write is what is
    # left, and it is reached the way the `~/.claude` floor above reaches its own — by patching
    # the first stage out. The alternative is a race nothing can schedule.
    #
    # Mutation (declared): the `except OSError` arm -> `except UnsafePath` (a second, dead
    # copy) -> the `OSError` escapes again and this reddens on `Refusal` not being raised.
    monkeypatch.setattr("keelline.setup.run._check_settings_parent", lambda settings: None)
    home = tmp_path / "home"
    missing = tmp_path / "not-there" / "settings.json"
    with pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "machine.toml",
            runner=FakeRunner(),
            yes=False,
            overlay=None,
            project_root=tmp_path / "project",
            settings=missing,
        )
    message = str(refused.value)
    assert str(missing) in message
    assert "FileNotFoundError" in message
    assert "has to exist and be a real directory" in message


def test_a_settings_path_inside_a_symlinked_directory_is_a_refusal_and_not_an_internal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The other half of item 2, and the layout `--settings` is advertised for one door over:
    # `--settings ~/.claude/settings.json` where `~/.claude` is itself the stow link. The walk
    # carries `O_NOFOLLOW`, so the root open refuses the link — and refused it as a bare
    # `OSError` rather than as `UnsafePath`, for the same reason as above. The first stage is
    # patched out for the reason the case above gives: it now refuses a symlinked directory too,
    # and this one is the floor beneath it.
    monkeypatch.setattr("keelline.setup.run._check_settings_parent", lambda settings: None)
    home = tmp_path / "home"
    real = tmp_path / "dotfiles" / "claude"
    real.mkdir(parents=True)
    linked = tmp_path / "linked-claude"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "machine.toml",
            runner=FakeRunner(),
            yes=False,
            overlay=None,
            project_root=tmp_path / "project",
            settings=linked / "settings.json",
        )
    message = str(refused.value)
    assert str(linked / "settings.json") in message
    assert "has to exist and be a real directory" in message
    # The file the link leads to is untouched: a refusal that had already written would be the
    # defect this one replaces, one step later.
    assert not (real / "settings.json").exists()


def test_a_settings_path_that_is_itself_a_symlink_is_refused_and_the_link_survives(
    tmp_path: Path,
) -> None:
    # The layout the flag is advertised for, with the path a person actually types: `stow`
    # folds as far as it can, so with `~/.claude` already there it links the *file*, and
    # `--settings ~/.claude/settings.json` names the link. `_check_settings_parent` asked only
    # about the directory, and `fsops.write_within` reaches `os.replace`, which REPLACES a
    # symlink entry rather than following or refusing it — so the link became a regular file,
    # the dotfiles copy kept its old bytes, and the command exited 0. Three surfaces said it
    # was refused: the comment beside the write, `docs/cli.md`, and the changelog.
    #
    # Measured before the fix: `is_symlink()` went `True -> False` and the dotfiles file was
    # still `{"mine": true}`. Both assertions below are that measurement.
    #
    # Mutation (declared, "setup --settings asks about the directory and not the file"): the
    # `contained` call goes -> the write lands, the link is replaced, and `pytest.raises`
    # reddens with `DID NOT RAISE`.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    machine = tmp_path / "machine.toml"
    real = tmp_path / "dotfiles" / "claude" / "settings.json"
    real.parent.mkdir(parents=True)
    real.write_text('{"mine": true}\n', encoding="utf-8")
    link = home / USER_SETTINGS
    link.symlink_to(real)
    with pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=FakeRunner(),
            yes=False,
            overlay=None,
            project_root=tmp_path / "project",
            settings=link,
        )
    message = str(refused.value)
    assert str(link) in message
    # The way out names the file to pass instead, the way `_check_settings_path`'s does.
    assert str(real) in message
    assert link.is_symlink(), "the link was replaced rather than refused"
    assert json.loads(real.read_text(encoding="utf-8")) == {"mine": True}
    assert not machine.exists()


def test_a_settings_path_that_is_an_existing_directory_is_refused_before_anything_is_written(
    tmp_path: Path,
) -> None:
    # The mirror of the case above, and the standing defect class in the function whose
    # docstring says it has been eliminated: a directory at `--settings` passed the early check
    # — `parent.is_dir() and not parent.is_symlink()` is true of it — and failed from inside
    # `_write_user_settings`, after `home.mkdir(parents=True)` and after the machine
    # configuration had been written. The `Refusal` is therefore NOT what this case is about:
    # the `except OSError` arm produces one either way, and what reddens under the declared
    # mutation is the two `exists()` assertions.
    #
    # Mutation (declared, "setup --settings accepts a directory where the file goes"): the
    # `is_dir()` refusal goes -> the run writes the home tree and the machine file before
    # `os.replace` reports `IsADirectoryError`, and both assertions below redden.
    home = tmp_path / "home"
    machine = tmp_path / "machine.toml"
    directory = tmp_path / "claude" / "settings.json"
    directory.mkdir(parents=True)
    with pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=FakeRunner(),
            yes=False,
            overlay=None,
            project_root=tmp_path / "project",
            settings=directory,
        )
    assert str(directory) in str(refused.value)
    assert "is a directory" in str(refused.value)
    assert not home.exists(), sorted(p.name for p in home.rglob("*"))
    assert not machine.exists()
