"""The `guard`, `commit` and `test` groups (§5.2).

`guard bg-cleanup` is the fail-closed row: it reads one JSON object on stdin — a whole hook
payload, or a bare `tool_input` — and refuses anything it cannot read with exit 2, because a
guard that guessed at plain text would be guessing. A deny is a `Refusal` (2); the restore
advisory is a finding (1); a clean command is 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from keelline.areas import SubParsers
from keelline.errors import Refusal
from keelline.result import Result

_UNREADABLE = "guard bg-cleanup reads one JSON object on stdin: a hook payload or a tool_input"
_CLEAN = "no background leak and no trailing restore"


_NOT_BASH = "not a Bash call; nothing to judge"


def _tool_input(raw: str) -> dict[str, Any] | None:
    """The Bash input to judge, or None for a whole payload naming another tool."""
    try:
        payload = json.loads(raw or "")
    except ValueError as exc:
        raise Refusal(f"{_UNREADABLE}; {exc}") from None
    if not isinstance(payload, dict):
        raise Refusal(_UNREADABLE)
    if "tool_name" in payload and payload["tool_name"] != "Bash":
        return None  # the handler is silent here too (`hooks.bash_command`)
    tool_input = payload.get("tool_input", payload)
    if not isinstance(tool_input, dict) or not isinstance(tool_input.get("command"), str):
        raise Refusal(f"{_UNREADABLE}, and the object must carry a string `command`")
    return tool_input


def run_bg_cleanup(args: argparse.Namespace) -> Result:
    from keelline.guards.bgcleanup import judge

    tool_input = _tool_input(sys.stdin.read())
    if tool_input is None:
        return Result(_NOT_BASH, {"hint": None})
    background = tool_input.get("run_in_background") is True
    verdict = judge(str(tool_input["command"]), background=background)
    if verdict.deny is not None:
        raise Refusal(verdict.deny)
    if verdict.hint is not None:
        return Result(verdict.hint, {"hint": verdict.hint}, exit_code=1)
    return Result(_CLEAN, {"hint": None})


def register(groups: SubParsers) -> None:
    guard = groups.add_parser("guard", help="fail-closed guards over a tool call")
    guard_sub = guard.add_subparsers(dest="command", metavar="<command>")
    bg = guard_sub.add_parser("bg-cleanup", help="judge a Bash call for a background leak")
    bg.set_defaults(func=run_bg_cleanup)
