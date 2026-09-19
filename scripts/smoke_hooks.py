#!/usr/bin/env python3
"""Feed every `hooks/hooks.json` entry the event it is filed under, through the wrapper.

    python3 scripts/smoke_hooks.py --plugin-root R --fixture F --scratch S

`R` is a plugin root — the checkout, or the copy the harness installed (DC8). One row per
entry and sample; exit 1 on any row whose exit code, stderr or stdout shape is not the one
the policy and the dispatcher's contract require.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"


@dataclass(frozen=True)
class Sample:
    payload: dict[str, object]
    expected_code: int
    stderr_required: bool
    label: str


SAMPLES: dict[str, tuple[Sample, ...]] = {
    "SessionStart": (Sample({"source": "startup"}, 0, False, "a session starts"),),
    "PreToolUse": (
        Sample(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "sleep 300 & wait", "run_in_background": True},
            },
            2,
            True,
            "a leaking background command is refused with a reason",
        ),
        Sample(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            0,
            False,
            "an ordinary command is allowed",
        ),
    ),
    "PostToolUse": (
        Sample(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "uv run pytest -q"},
                "tool_response": {"exit_code": 1},
            },
            0,
            False,
            "a failed test run is annotated, never blocked",
        ),
    ),
}


def entries(plugin_root: Path) -> list[tuple[str, str]]:
    document = json.loads((plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    return [
        (event, entry["command"])
        for event, groups in document["hooks"].items()
        for group in groups
        for entry in group["hooks"]
    ]


def fixture_repository(fixture: Path, into: Path) -> Path:
    """A copy of the fixture as a committed repository, which is what the wrapper resolves."""
    shutil.copytree(fixture, into)
    env = {
        "PATH": "/usr/bin:/bin",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    for args in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "fixture"],
    ):
        subprocess.run(["git", "-C", str(into), *args], check=True, capture_output=True, env=env)  # noqa: S603, S607
    return into


def check_entry(
    event: str,
    command: str,
    sample: Sample,
    *,
    plugin_root: Path,
    project: Path,
    home: Path,
    data: Path,
) -> str | None:
    argv = shlex.split(command.replace(PLACEHOLDER, str(plugin_root)))
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("KEELLINE_", "XDG_", "CLAUDE_", "PLUGIN_"))
    }
    env.update(
        {
            "HOME": str(home),
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
            "CLAUDE_PROJECT_DIR": str(project),
            "CLAUDE_PLUGIN_DATA": str(data),
        }
    )
    payload = {
        "session_id": "smoke",
        "cwd": str(project),
        "hook_event_name": event,
        **sample.payload,
    }
    done = subprocess.run(  # noqa: S603
        argv,
        input=json.dumps(payload),
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if done.returncode != sample.expected_code:
        return (
            f"exited {done.returncode}, expected {sample.expected_code}; "
            f"stderr: {done.stderr.strip()[:200]}"
        )
    if sample.stderr_required and not done.stderr.strip():
        return "refused with no reason on stderr"
    # Only the dispatcher's own entries (`… hook <event>`) speak JSON; the ten
    # `memory session-context` entries print a bundle as prose, which is how they inject it.
    if "hook" in argv and done.stdout.strip():
        try:
            emitted = json.loads(done.stdout)
        except json.JSONDecodeError:
            return "stdout is not JSON"
        if emitted.get("hookSpecificOutput", {}).get("hookEventName") != event:
            named = emitted.get("hookSpecificOutput", {}).get("hookEventName")
            return f"stdout names {named!r}, not {event!r}"
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("--plugin-root", "--fixture", "--scratch"):
        parser.add_argument(flag, required=True, type=Path)
    args = parser.parse_args(argv)
    # Resolved, because every subprocess below runs with `cwd=project`: a relative plugin root
    # would be looked for inside the fixture, which is the one tree it is never in.
    args.plugin_root = args.plugin_root.resolve()
    args.fixture = args.fixture.resolve()
    args.scratch = args.scratch.resolve()
    project = fixture_repository(args.fixture, args.scratch / "project")
    home, data = args.scratch / "home", args.scratch / "data"
    home.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    wrapper = args.plugin_root / "hooks" / "run-hook.sh"
    failures = 0
    if not os.access(wrapper, os.X_OK):
        print(f"FAIL  {wrapper} is not executable")
        failures += 1
    found = entries(args.plugin_root)
    if not found:
        print("FAIL  no hook entries at all")
        return 1
    # An event with no sample would contribute zero rows and a green summary — the vacuous
    # shape this repository names; a sixth event fails here until it has a sample.
    unsampled = {event for event, _ in found} - SAMPLES.keys()
    if unsampled:
        print(f"FAIL  no sample event for {sorted(unsampled)}")
        return 1
    for event, command in found:
        for sample in SAMPLES.get(event, ()):
            problem = check_entry(
                event,
                command,
                sample,
                plugin_root=args.plugin_root,
                project=project,
                home=home,
                data=data,
            )
            mark = "ok  " if problem is None else "FAIL"
            tail = command.split("run-hook.sh")[-1].strip().lstrip('" ')
            why = f" -> {problem}" if problem else ""
            print(f"{mark}  {event:<13} {sample.label}: {tail}{why}")
            failures += problem is not None
    print(f"{len(found)} entries, {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
