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
from pathlib import Path
from typing import TYPE_CHECKING, Any

from keelline import fsops
from keelline.areas import SubParsers
from keelline.config.loader import load
from keelline.errors import Failure, Refusal
from keelline.result import Result

if TYPE_CHECKING:
    from keelline.config.schema import Config

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


_STRIP_REMEDY = (
    "Rewrite the messages without the trailer (`git rebase -i --exec 'git commit --amend "
    "--no-edit' <base>`, or `git commit --amend` for the last one). `keelline setup "
    "--git-hooks` installs the hook that strips these before a commit is written."
)

# git's own default for `core.commentChar` (the `prepare-commit-msg` comment block). Not read
# from the repository's config: a value this module would feed straight into a line-prefix
# comparison is exactly the kind of config value §3 calls untrusted, and there is no subprocess
# guard to put around a plain string compare. A repository that changed the default gets no
# split and therefore no strip on that file — a no-op, not a corruption.
_COMMENT_CHAR = "#"


def _split_trailing_comment_block(text: str) -> tuple[str, str]:
    """Split a `prepare-commit-msg` file into `(message region, trailing comment block)`.

    The comment block is the run of lines at the end of `text` whose first character is
    `_COMMENT_CHAR`, together with any blank lines between or after them. `commit.py` must
    never learn about `#`: in a message read from `git log` a `#` line is real content, so this
    split lives here, on the file-reading side, not in the module that judges the message text.

    `offending_lines`/`strip_message` judge only a message's *final paragraph* (see
    `commit.py`'s docstring), and in an ordinary interactive commit that final paragraph is
    git's own comment block, not whatever a person or a tool wrote above it — so stripping the
    file's text whole would no-op on exactly the file `prepare-commit-msg` hands the hook.
    """
    lines = text.splitlines(keepends=True)
    index = len(lines)
    while index > 0 and (
        lines[index - 1].strip() == "" or lines[index - 1].startswith(_COMMENT_CHAR)
    ):
        index -= 1
    if not any(line.startswith(_COMMENT_CHAR) for line in lines[index:]):
        index = len(lines)  # no comment line back there; nothing to split off
    return "".join(lines[:index]), "".join(lines[index:])


def _root_and_config(args: argparse.Namespace) -> tuple[Path, Config]:
    root = Path(args.root).resolve()
    machine = Path(args.machine) if getattr(args, "machine", None) else None
    return root, load(root, machine=machine)


def run_commit_check(args: argparse.Namespace) -> Result:
    from keelline.guards.commit import check_range

    root, config = _root_and_config(args)
    report = check_range(root, str(args.rev_range), config)
    data = {
        "commits": report.commits,
        "violations": [
            {"sha": v.sha, "offences": [{"line": o.line, "label": o.label} for o in v.offences]}
            for v in report.violations
        ],
    }
    if not report.violations:
        return Result(f"OK: {report.commits} commit message(s) checked", data)
    items = "; ".join(
        f"{v.sha[:12]} line {o.line} [{o.label}]" for v in report.violations for o in v.offences
    )
    return Result(
        f"FAIL: {len(report.violations)} of {report.commits} commit message(s) carry an "
        f"attribution trailer: {items}. {_STRIP_REMEDY}",
        data,
        exit_code=1,
    )


def run_commit_strip(args: argparse.Namespace) -> Result:
    from keelline.guards.commit import offending_lines, strip_message

    raw = str(args.file)
    if raw.startswith("-"):
        raise Refusal(f"{raw!r} looks like an option, not a file")
    path = Path(raw)
    if path.is_symlink():
        raise Refusal(f"{path} is a symlink; refusing to write through it")
    # `--root` elsewhere is never `-`-checked and is safe only because `Path(...).resolve()`
    # makes it absolute before any `git -C` sees it; this argument is not resolved, so it is.
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Failure(f"cannot read {path}: {exc}") from None
    message, comment_block = _split_trailing_comment_block(original)
    stripped_message = strip_message(message)
    # A message that is *only* attribution would be emptied, which aborts the commit with a
    # confusing "empty message" error. Leave it alone and let CI explain.
    if not stripped_message.strip() or stripped_message == message:
        return Result("nothing to strip", {"stripped": 0})
    count = len(offending_lines(message))
    fsops.write_atomically(path, stripped_message + comment_block)
    return Result(f"stripped {count} attribution line(s) from {path}", {"stripped": count})


def register(groups: SubParsers) -> None:
    guard = groups.add_parser("guard", help="fail-closed guards over a tool call")
    guard_sub = guard.add_subparsers(dest="command", metavar="<command>")
    bg = guard_sub.add_parser("bg-cleanup", help="judge a Bash call for a background leak")
    bg.set_defaults(func=run_bg_cleanup)

    commit = groups.add_parser("commit", help="commit-message rules")
    commit_sub = commit.add_subparsers(dest="command", metavar="<command>")
    check = commit_sub.add_parser("check", help="check every message in a revision range")
    check.add_argument("--range", dest="rev_range", required=True, help="e.g. main..HEAD")
    check.add_argument("--root", default=".", help="project root (default: current directory)")
    check.add_argument("--machine", default=None, help="machine configuration file to read")
    check.set_defaults(func=run_commit_check)
    strip = commit_sub.add_parser("strip", help="strip attribution lines from a message file")
    strip.add_argument("file", help="the commit-message file git handed the hook")
    strip.set_defaults(func=run_commit_strip)
