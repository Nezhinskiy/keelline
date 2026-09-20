from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from keelline.cli import build_parser, discover_registrars
from keelline.guards.hooks import BASH
from keelline.hooks.api import EVENTS
from keelline.hooks.registry import discover

# `keelline.memory.api` and not `keelline.memory.bundles`: an area is imported through its
# published surface, never through a private module, and `api.py`'s own docstring names this
# lane as the reason `SLOTS` is on the list — "`hooks-core` needs the bundle slots".
from keelline.memory.api import SLOTS

ROOT = Path(__file__).resolve().parents[2]
HOOKS = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
WRAPPER = '"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh"'


def _entries() -> list[tuple[str, str, dict[str, Any]]]:
    """Every entry with the event key it is filed under **and** its group's matcher.

    The matcher used to be dropped here, and `type` was read by nothing at all. Both are the
    entry's own fields and both decide whether it ever runs: the reviewer changed `"matcher":
    "Bash"` to `"bash"` -- which retires `bg-cleanup`, the plugin's only fail-closed guard --
    and `"type": "command"` to `"commandd"`, and every one of the ten assertions below passed.
    A walk that discards a field is a walk that cannot be asked about it.
    """
    return [
        (event, group.get("matcher", ""), entry)
        for event, groups in HOOKS["hooks"].items()
        for group in groups
        for entry in group["hooks"]
    ]


# The `source` values Claude Code sends on SessionStart. Dropping one from the matcher silences
# every injection bundle for that kind of session start -- `resume` and `compact` are the two a
# long session actually hits -- with nothing else anywhere saying so.
SESSION_SOURCES = {"startup", "resume", "clear", "compact", "fork"}


def test_there_are_entries_at_all() -> None:
    # The non-vacuity guard every walk-driven assertion below depends on: an empty `hooks`
    # object satisfies all six of them.
    assert len(_entries()) == 13


def test_every_command_parses_against_the_real_parser() -> None:
    # A shipped file no type checker reads. The failure mode it prevents is the expensive one:
    # a typo here is discovered by a user whose guard silently stopped guarding.
    parser = build_parser(discover_registrars())
    for _, _matcher, entry in _entries():
        words = entry["command"].split()
        assert words[0] == WRAPPER
        assert words[1] in {"open", "closed"}
        parser.parse_args(words[2:])


def test_no_entry_passes_json() -> None:
    # `bundles.py`'s CAP_MARGIN comment, addressing this lane by name: "the `hooks.json`
    # entries must not pass `--json`. The margin is additive only because `memory
    # session-context` prints the text raw." `memory/commands.py` records that this invariant
    # was "owned by a different lane, asserted by no test here". This is that test.
    for _, _matcher, entry in _entries():
        assert "--json" not in entry["command"].split()


def test_there_is_one_session_start_entry_per_declared_bundle_slot() -> None:
    # §9.5: a bundle that overflows is split across further entries, and raising N edits this
    # shipped file — so N is asserted from SLOTS rather than counted by hand.
    declared = {
        (words[words.index("--bundle") + 1], words[words.index("--part") + 1])
        for event, _matcher, entry in _entries()
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
    for _, _matcher, entry in _entries():
        words = entry["command"].split()
        if words[2] == "hook":
            assert words[3] in events


def test_every_registered_handler_has_an_entry() -> None:
    # The other direction, and the more expensive one to get wrong: a handler with no entry
    # never runs. If `worktree-link` were the one left out, every bundle in every worktree
    # would be empty and this wave's own smoke check could not see it.
    dispatched = {
        words[3]
        for _, _matcher, entry in _entries()
        if (words := entry["command"].split())[2] == "hook"
    }
    assert {handler.event for handler in discover()} <= dispatched


def test_only_pre_tool_use_entries_may_be_closed() -> None:
    # D11: fail-closed is expressible only where the platform blocks on exit 2. On
    # SessionStart exit codes are ignored and on UserPromptSubmit exit 2 erases the prompt, so
    # a `closed` entry there is a refusal that either does nothing or destroys the user's input.
    for event, _matcher, entry in _entries():
        if entry["command"].split()[1] == "closed":
            assert event == "PreToolUse"


def test_no_entry_is_async() -> None:
    # Codex async hooks cannot block (§5.3). Unmeasured by the spikes — which is a reason to
    # hold the line in the file, not a reason to test it against the platform.
    for _, _matcher, entry in _entries():
        assert entry.get("async") is not True


def test_session_start_entries_declare_the_codex_spill_key() -> None:
    # S1 measured that both harnesses tolerate this key at install time on both events. It also
    # measured NO cap verdict for it: a 20-character canary cannot separate an ignored key from
    # one honoured with 0 meaning unlimited. So it is declared and relied on for nothing — the
    # bound that IS measured is `bundles._cap`'s margin under `hook_output_chars` (S7).
    for event, _matcher, entry in _entries():
        if event == "SessionStart":
            assert entry.get("additionalContextLimit") == 0


def test_every_entry_is_a_command_entry() -> None:
    # `type` is what tells the harness this entry is a command to run at all. Nothing read it:
    # `"type": "commandd"` shipped green, and an entry the harness cannot classify is a guard
    # that silently never fires -- the same failure mode as a mistyped event, one field over.
    #
    # Mutation: `"type": "command"` -> `"commandd"` on any entry in hooks/hooks.json -> reddens.
    for _, _matcher, entry in _entries():
        assert entry["type"] == "command", entry


def test_every_tool_matched_entry_matches_the_name_both_handlers_filter_on() -> None:
    # `guards.hooks.BASH` is the name `bash_command` compares `event.tool_name` against, so the
    # matcher in this file and that constant are two spellings of one thing. The matcher is a
    # case-sensitive regular expression: `"bash"` matches no tool Claude Code or Codex reports,
    # which retires `bg-cleanup` -- the plugin's only `Policy.CLOSED` handler -- and the
    # `test-hygiene` notice with it, permanently and silently.
    #
    # Asserted from the constant rather than spelled here, for the reason
    # `test_there_is_one_session_start_entry_per_declared_bundle_slot` gives about SLOTS.
    #
    # Mutation: `"matcher": "Bash"` -> `"bash"` in hooks/hooks.json -> reddens.
    matched = {
        matcher for event, matcher, _ in _entries() if event in {"PreToolUse", "PostToolUse"}
    }
    assert matched == {BASH}


def test_the_session_start_matcher_carries_every_source_a_session_can_start_from() -> None:
    # The same field on the other event, where it selects `source` rather than a tool. A source
    # dropped from this alternation is every injection bundle missing from that kind of session
    # start -- `resume` and `compact` are the two a long session actually reaches -- reported
    # by nothing, because a hook that is not invoked emits no diagnostic.
    #
    # Mutation: delete `|resume` from the SessionStart matcher in hooks/hooks.json -> reddens.
    matchers = {matcher for event, matcher, _ in _entries() if event == "SessionStart"}
    assert len(matchers) == 1, matchers
    assert set(matchers.pop().split("|")) == SESSION_SOURCES


def test_every_entry_is_filed_under_the_event_its_command_dispatches() -> None:
    # Both event tests above read the event out of the *argv* and never out of the JSON key it
    # is filed under, so `"PostToolUSe"` as a key passed every one of them: the command still
    # said `hook PostToolUse` and still named a registered handler, while the harness -- which
    # dispatches on the key -- emitted nothing for it ever again. The key is what runs the
    # entry, so the key is what is asserted, against `hooks.api.EVENTS` and against the argv.
    #
    # Mutation: rename the `"PostToolUse"` key to `"PostToolUSe"` in hooks/hooks.json -> reddens.
    keys = list(HOOKS["hooks"])
    assert keys, "no event keys at all, so the assertions below measure nothing"
    for key in keys:
        assert key in EVENTS, key
    for event, _matcher, entry in _entries():
        words = entry["command"].split()
        if words[2] == "hook":
            assert words[3] == event, entry["command"]
