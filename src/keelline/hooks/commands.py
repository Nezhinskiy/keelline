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
from keelline.hooks.policy import refuses_on_internal_error
from keelline.hooks.registry import discover
from keelline.hooks.sink import sink_for
from keelline.presets import load_preset

# Fixed text, never the link's target: what a link in the project's root points at is the
# repository's choice. Asked of the name itself (`is_symlink`) and before any `is_file`, which
# follows the link, so the answer does not depend on the target: followed, a link to a regular
# file would reach the loader's refusal as an internal error, and one to `/dev/zero` would read
# as no file at all.
LINKED = (
    "keelline: keelline.toml is a symbolic link, and no Keelline command reads keelline.toml "
    "through one; replace the link with the file itself"
)


def _linked(event_name: str) -> int:
    """A symlinked `keelline.toml`: refused where an internal error refuses, open elsewhere.

    The same verdict per event as a `keelline.toml` that does not load, in words that name the
    rule rather than an exception; no handler runs on any event.
    """
    if refuses_on_internal_error(event_name):
        sys.stderr.write(f"{LINKED}; refused\n")
        return 2
    sys.stderr.write(f"{LINKED}; continuing open\n")
    return 0


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
        document = None if root is None else root / CONFIG_FILE
        if document is not None and document.is_symlink():
            return _linked(event_name)
        if root is not None and document is not None and document.is_file():
            # `interactive=False`, said rather than sniffed. A hook's stdin is a pipe, so
            # the terminal check happens to answer the same thing — but the gate on
            # `KEELLINE_CONFIG` and `XDG_CONFIG_HOME` is the one that decides which
            # overlay root and which `trust.json` this process reads, and it should not
            # rest on a property of how the harness happens to invoke us.
            config = load(root, interactive=False)
        cap = _output_cap(config)
        # Keyed on the session the payload named, so `once_key` means "once per context"
        # rather than "every invocation", and a handler's failure reaches `doctor` instead of
        # being discarded. `sink_for` answers `NullSink()` whenever there is no writable data
        # directory — outside a harness, or on a read-only one — because a hook runs on every
        # tool call and a sink failure must cost a marker, never the call.
        outcome = dispatch(
            event, discover(), config, sink=sink_for(event.session_id, os.environ), cap=cap
        )
    except BaseException as exc:  # an internal error must never read as permission
        reason = f"keelline: internal error: {type(exc).__name__}: {exc}"
        if refuses_on_internal_error(event_name):
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
