from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from keelline.cli import build_parser, discover_registrars
from keelline.hooks.registry import discover

# `keelline.memory.api` and not `keelline.memory.bundles`: an area is imported through its
# published surface, never through a private module, and `api.py`'s own docstring names this
# lane as the reason `SLOTS` is on the list — "`hooks-core` needs the bundle slots".
from keelline.memory.api import SLOTS

ROOT = Path(__file__).resolve().parents[2]
HOOKS = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
WRAPPER = '"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh"'


def _entries() -> list[tuple[str, dict[str, Any]]]:
    return [
        (event, entry)
        for event, groups in HOOKS["hooks"].items()
        for group in groups
        for entry in group["hooks"]
    ]


def test_there_are_entries_at_all() -> None:
    # The non-vacuity guard every walk-driven assertion below depends on: an empty `hooks`
    # object satisfies all six of them.
    assert len(_entries()) == 13


def test_every_command_parses_against_the_real_parser() -> None:
    # A shipped file no type checker reads. The failure mode it prevents is the expensive one:
    # a typo here is discovered by a user whose guard silently stopped guarding.
    parser = build_parser(discover_registrars())
    for _, entry in _entries():
        words = entry["command"].split()
        assert words[0] == WRAPPER
        assert words[1] in {"open", "closed"}
        parser.parse_args(words[2:])


def test_no_entry_passes_json() -> None:
    # `bundles.py`'s CAP_MARGIN comment, addressing this lane by name: "the `hooks.json`
    # entries must not pass `--json`. The margin is additive only because `memory
    # session-context` prints the text raw." `memory/commands.py` records that this invariant
    # was "owned by a different lane, asserted by no test here". This is that test.
    for _, entry in _entries():
        assert "--json" not in entry["command"].split()


def test_there_is_one_session_start_entry_per_declared_bundle_slot() -> None:
    # §9.5: a bundle that overflows is split across further entries, and raising N edits this
    # shipped file — so N is asserted from SLOTS rather than counted by hand.
    declared = {
        (words[words.index("--bundle") + 1], words[words.index("--part") + 1])
        for event, entry in _entries()
        if event == "SessionStart" and "--bundle" in (words := entry["command"].split())
    }
    assert declared == {
        (bundle.value, str(part)) for bundle, parts in SLOTS.items() for part in range(1, parts + 1)
    }


def test_every_dispatched_event_has_at_least_one_handler() -> None:
    # An entry for an event nothing handles spawns a process to emit an empty envelope, and
    # looks installed in doctor's listing. §5.3's table names five events; three of them have
    # no handler in this build, and the lane that adds one adds its entry.
    events = {handler.event for handler in discover()}
    for _, entry in _entries():
        words = entry["command"].split()
        if words[2] == "hook":
            assert words[3] in events


def test_every_registered_handler_has_an_entry() -> None:
    # The other direction, and the more expensive one to get wrong: a handler with no entry
    # never runs. If `worktree-link` were the one left out, every bundle in every worktree
    # would be empty and this wave's own smoke check could not see it.
    dispatched = {
        words[3] for _, entry in _entries() if (words := entry["command"].split())[2] == "hook"
    }
    assert {handler.event for handler in discover()} <= dispatched


def test_only_pre_tool_use_entries_may_be_closed() -> None:
    # D11: fail-closed is expressible only where the platform blocks on exit 2. On
    # SessionStart exit codes are ignored and on UserPromptSubmit exit 2 erases the prompt, so
    # a `closed` entry there is a refusal that either does nothing or destroys the user's input.
    for event, entry in _entries():
        if entry["command"].split()[1] == "closed":
            assert event == "PreToolUse"


def test_no_entry_is_async() -> None:
    # Codex async hooks cannot block (§5.3). Unmeasured by the spikes — which is a reason to
    # hold the line in the file, not a reason to test it against the platform.
    for _, entry in _entries():
        assert entry.get("async") is not True


def test_session_start_entries_declare_the_codex_spill_key() -> None:
    # S1 measured that both harnesses tolerate this key at install time on both events. It also
    # measured NO cap verdict for it: a 20-character canary cannot separate an ignored key from
    # one honoured with 0 meaning unlimited. So it is declared and relied on for nothing — the
    # bound that IS measured is `bundles._cap`'s margin under `hook_output_chars` (S7).
    for event, entry in _entries():
        if event == "SessionStart":
            assert entry.get("additionalContextLimit") == 0
