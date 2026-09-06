"""What a Keelline *internal error* costs on each hook event (§5.3).

Keelline's own policy, not the platform's: the platform also acts on exit 2 for
`UserPromptSubmit`, `Stop` and `SubagentStop`, but only `PreToolUse` refuses on an internal
error, because a broken Keelline must not wedge the user everywhere else — on
`UserPromptSubmit` exit 2 erases what the user typed, which is why §5.3 puts no guard there.
A handler's deny is a decision, not a breakage, and refuses on every event.

A leaf module: the frame reads it too. A discovery failure aborts `keelline.cli.main` before
argparse can dispatch `hook`, so the frame must judge that failure by this same rule instead
of exiting 2 blindly. Nothing here imports the rest of the package, so the frame pays no area
import to reach it.
"""

from __future__ import annotations

BLOCKING_EVENTS = frozenset({"PreToolUse"})


def refuses_on_internal_error(event_name: str) -> bool:
    return event_name in BLOCKING_EVENTS


def hook_event_name(argv: list[str]) -> str | None:
    """The event a `keelline hook <event>` line names, read before a parser can be built."""
    words = [arg for arg in argv if arg != "--json"]
    if len(words) >= 2 and words[0] == "hook":
        return words[1]
    return None
