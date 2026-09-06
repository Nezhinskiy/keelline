"""`keelline hook <event>`: stdin in, JSON out, the exit code owned here and event-aware."""

from __future__ import annotations

import argparse
import json
import os
import sys

from keelline.areas import SubParsers
from keelline.config.loader import CONFIG_FILE, load
from keelline.config.schema import Config
from keelline.hooks.dispatch import dispatch, parse_event
from keelline.hooks.registry import discover
from keelline.presets import load_preset

# Keelline's own policy, not the platform's: the platform also acts on exit 2 for
# UserPromptSubmit, Stop and SubagentStop, but only PreToolUse refuses on an INTERNAL
# error, because a broken Keelline must not wedge the user everywhere else. A handler's
# deny is a decision, not a breakage, and refuses on every event.
BLOCKING_EVENTS = frozenset({"PreToolUse"})


def _output_cap(config: Config | None) -> int:
    """The platform cap is a shipped constant; a repository without a config still gets it."""
    if config is not None:
        return config.native_caps.hook_output_chars
    return int(load_preset("recommended")["native_caps"]["hook_output_chars"])


def run_hook(args: argparse.Namespace) -> int:
    event_name = str(args.event)
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("hook payload is not a JSON object")
        # argv is authoritative: the wrapper controls it, while stdin is the untrusted side.
        payload["hook_event_name"] = event_name
        event = parse_event(payload, env=os.environ)
        config = None
        root = event.project_root
        if root is not None and (root / CONFIG_FILE).is_file():
            config = load(root)
        cap = _output_cap(config)
        outcome = dispatch(event, discover(), config, cap=cap)
    except Exception as exc:  # an internal error must never read as permission
        reason = f"keelline: internal error: {type(exc).__name__}: {exc}"
        if event_name in BLOCKING_EVENTS:
            sys.stderr.write(f"{reason}; refused\n")
            return 2
        sys.stderr.write(f"{reason}; continuing open\n")
        return 0
    if outcome.stdout:
        sys.stdout.write(outcome.stdout)
    if outcome.stderr:
        sys.stderr.write(outcome.stderr)
    return outcome.exit_code


def register(groups: SubParsers) -> None:
    group = groups.add_parser("hook", help="dispatch one harness hook event (internal)")
    group.add_argument("event", help="hook event name, e.g. SessionStart")
    group.set_defaults(func=run_hook)
