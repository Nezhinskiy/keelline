"""The two smoke scripts, run here against the checkout as the plugin root.

CI runs them against the INSTALLED copy (DC8); this proves the scripts' own logic — that a
mismatch is reported and a match is not — so a green CI row means the plugin, not the script.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@needs_git
def test_every_hook_entry_answers_its_sample_event_through_the_checkout(tmp_path: Path) -> None:
    # S8's matrix lives in tests/hooks/test_wrapper.py; this is the positive row per entry:
    # every `hooks.json` command, fed the event it is filed under, exits as the policy says.
    # The closed `PreToolUse` entry is fed a leaking background command and must exit 2 with
    # a reason; every open entry exits 0.
    smoke = _load("smoke_hooks")
    code = smoke.main(
        [
            "--plugin-root",
            str(ROOT),
            "--fixture",
            str(ROOT / "tests" / "fixtures" / "smoke-project"),
            "--scratch",
            str(tmp_path),
        ]
    )
    assert code == 0


@needs_git
def test_a_wrapper_that_answers_wrongly_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The script's own oracle: a plugin root whose wrapper exits 0 on everything must make
    # the closed row fail. Mutation (declared): drop the `expected != done.returncode`
    # comparison in `smoke_hooks.check_entry` -> this passes with code 0 and reddens.
    smoke = _load("smoke_hooks")
    planted = tmp_path / "plugin"
    shutil.copytree(ROOT / "hooks", planted / "hooks")
    (planted / "scripts").mkdir()
    (planted / "scripts" / "keelline").write_text("raise SystemExit(0)\n", encoding="utf-8")
    code = smoke.main(
        [
            "--plugin-root",
            str(planted),
            "--fixture",
            str(ROOT / "tests" / "fixtures" / "smoke-project"),
            "--scratch",
            str(tmp_path),
        ]
    )
    assert code == 1
    out = capsys.readouterr().out
    assert "exited 0, expected 2" in out  # the closed row, for its own reason


@needs_git
def test_hooks_json_losing_an_event_fails_instead_of_running_fewer_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The guard held one direction. `unsampled = events - SAMPLES.keys()` catches `hooks.json`
    # GAINING an event with no sample; `hooks.json` LOSING one shrinks `found`, leaves
    # `unsampled` empty, runs fewer rows and prints a green summary — the entry stopped being
    # smoke-tested and the script said nothing. That is the vacuous shape this repository names,
    # arriving through the guard written to prevent it.
    #
    # `PostToolUse` is the event removed because it is the one with exactly one sample, so its
    # rows are the whole of what goes missing.
    #
    # Mutation (declared, "the hook smoke stops noticing an event that lost its entry"): the
    # `unentered` set is emptied -> the run proceeds on the remaining entries, every row passes,
    # `main` returns 0, and both assertions below redden.
    smoke = _load("smoke_hooks")
    planted = tmp_path / "plugin"
    shutil.copytree(ROOT / "hooks", planted / "hooks")
    shutil.copytree(ROOT / "scripts", planted / "scripts")
    entries = planted / "hooks" / "hooks.json"
    document = json.loads(entries.read_text(encoding="utf-8"))
    assert "PostToolUse" in document["hooks"], "the fixture removes an event that is there"
    del document["hooks"]["PostToolUse"]
    entries.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    code = smoke.main(
        [
            "--plugin-root",
            str(planted),
            "--fixture",
            str(ROOT / "tests" / "fixtures" / "smoke-project"),
            "--scratch",
            str(tmp_path),
        ]
    )
    assert code == 1
    assert "no hook entry for ['PostToolUse']" in capsys.readouterr().out


@needs_git
def test_the_exfiltration_scenario_holds_against_the_checkout(tmp_path: Path) -> None:
    # S10 (§14): a hostile clone with in-repo memory at `startup: -1`, a `project.name`
    # naming another project, and a committed settings `env` block naming a machine
    # configuration inside the clone and a PATH into the clone. Asserted separately: nothing
    # untrusted reaches the session-start output, the hook ignored the clone's
    # KEELLINE_CONFIG, the planted interpreter never ran, and `attach` refuses. The MCP arm
    # is not run: `mcp` is not in wave 3, and the script says so in its own output.
    exfil = _load("smoke_exfiltration")
    code = exfil.main(
        [
            "--plugin-root",
            str(ROOT),
            "--fixture",
            str(ROOT / "tests" / "fixtures" / "hostile-project"),
            "--scratch",
            str(tmp_path),
        ]
    )
    assert code == 0


@needs_git
def test_the_exfiltration_scenario_reports_a_row_that_went_the_wrong_way(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The same oracle for the other script, and the reason the scenario's first row is a
    # positive control: every other row asserts an ABSENCE, and a scenario whose pipeline is
    # broken prints the same absences. Here the canary note is emptied before the run, so the
    # control — the note reaching a session that has trusted it — is the row that goes red,
    # while the four negative rows stay green on a store with nothing in it.
    exfil = _load("smoke_exfiltration")
    fixture = tmp_path / "fixture"
    shutil.copytree(ROOT / "tests" / "fixtures" / "hostile-project", fixture)
    note = fixture / "docs" / "memory" / "developer" / "canary.md"
    note.write_text(
        note.read_text(encoding="utf-8").replace("CANARY-IN-REPO-RULE", "nothing"), "utf-8"
    )
    code = exfil.main(
        ["--plugin-root", str(ROOT), "--fixture", str(fixture), "--scratch", str(tmp_path / "s")]
    )
    assert code == 1
    out = capsys.readouterr().out
    assert "FAIL  the owner's own trust record lets the note through" in out, out
