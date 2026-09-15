"""Reject AI/tool attribution trailers in commit messages.

The rule this enforces is a developer policy, not a project convention, so it is deliberately
*not* restated here: this module owns the mechanism, not the norm.

Why a check rather than a note. A session whose context already held the rule as a memory note
— a note that links to the attribution rule by name — still emitted the trailer on seven
consecutive commits, because the agent harness places an instruction to append such a trailer
in the system prompt, adjacent to the git command being run. A rule delivered as context
competes with that instruction on every commit and only has to lose once. A check does not
compete: it runs after the message exists and is not part of any prompt.

Two surfaces share one pattern set, so they cannot drift apart:

* ``commit check --range A..B`` — CI, on every push and every pull request. The authoritative
  gate.
* ``commit strip FILE`` — the ``prepare-commit-msg`` hook that ``setup --git-hooks`` installs.
  Local and early, so the trailer is gone before the commit exists. ``git commit --no-verify``
  skips ``pre-commit`` and ``commit-msg`` but *not* ``prepare-commit-msg``, so this survives
  the usual bypass.

Adding a vendor means **all three** tables, not two: its word in ``_VENDORS``, which is what the
footer and marker rules read; its mail domain in ``_VENDOR_DOMAINS``; and its product name in
``_PRODUCTS``. The last two are both trailer-rule tables and neither subsumes the other — a
vendor whose mail domain does not spell its own product name (Windsurf sends from codeium.com)
needs the domain listed, and a vendor with no mail domain of its own can land **only** in
``_PRODUCTS``. That third table is the one a maintainer forgets, and forgetting it ships a
vendor uncovered on the trailer surface; the note beside ``_VENDOR_DOMAINS`` records which
vendor is in that state today and why widening the domain table is not the answer.

**Only the final paragraph is judged**, and that is this port's one deliberate divergence. Git
trailers and harness footers are appended at the end of a message, so the last paragraph is
the only place a real attribution can appear; everything above it is prose, and a repository
that uses coding agents writes that prose constantly — provider names, model ids, paths, and
quoted trailers in a message about this very policy. Judging the whole message let ``strip``
amputate a body sentence, which is the worse failure of the two: the range check still catches
a trailer the hook left behind, but nothing puts a deleted sentence back.

**Trailing blank lines are not the final paragraph.** The search for the paragraph separator
starts at the last *non-blank* line, because otherwise a message ending in a blank — or in a
line of nothing but spaces, which no editor shows — leaves an empty final paragraph, and a gate
whose whole point is that it cannot be bypassed is bypassed by one trailing space. That is a
measured defect of the first cut of this module, not a hypothetical.

The trailer rule reads the trailer's *value*, not the whole line: an address at a vendor's own
mail domain, or a whole name that is a product phrase. **The domain rule's cost is chosen, not
overlooked** — a person whose employer is a vendor (``alice@openai.com``) is indistinguishable
from that vendor's bot by address alone, and is flagged. Dropping the domain rule to spare them
would miss every bot whose trailer name is not a product phrase, which is most of them.

Scope and limits. Only whole lines that *are* an attribution trailer or footer are matched, so
a message discussing attribution in prose is untouched — and, symmetrically, a violation
phrased in prose rather than as a trailer is not caught. This checks commit messages only: it
never rewrites file content, where a matching line can legitimately be a fixture, a quoted
example, or documentation of this very policy. Pull-request bodies, review comments and branch
names are outside both surfaces here and remain on judgement.

Two further limits of the mechanism, neither of them reachable from ``git log``. Both functions
split with ``str.splitlines()`` and rejoin with a bare LF, so a message carrying CRLF or one of
the exotic Unicode line separators comes back normalised whenever anything is stripped — git
itself writes LF, so this needs a hand-authored message file to reach. And a trailer whose
value is folded across a continuation line is matched on its first line only; no harness emits
one today.

One consequence worth knowing: a commit message whose final paragraph quotes a forbidden
trailer as an example — plausible when editing this policy — fails the check. Describe the
trailer instead of pasting it.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from keelline.errors import Refusal
from keelline.gitenv import scrubbed_env

if TYPE_CHECKING:
    from keelline.config.schema import Config

# Vendor tokens are only ever used inside an anchored construct below, never on their own: a
# repository legitimately contains `claude_cli`, `claude-opus-5`, and prose about the
# subscription-backed provider, none of which may trip the check.
_VENDORS = (
    r"claude|anthropic|codex|openai|chatgpt|copilot|cursor|gemini|devin"
    r"|windsurf|codeium|mistral|aider"
)

# A `-by:` trailer: any `<Something>-by:` key, because Reviewed-by, Signed-off-by and
# Tested-by are all used by agent harnesses; the value is what decides. A value folded onto a
# continuation line is read to the end of the first line only (see the docstring).
_TRAILER = re.compile(r"^[ \t]*[\w-]*-by:[ \t]*(?P<value>.+?)[ \t]*$", re.IGNORECASE)
# The address rule: the bot's own domain. A person employed there is the documented cost.
# Two domains are deliberately absent, for one reason: `github.com` is what GitHub puts on
# ordinary human web-UI commits, and `google.com` is the address of every Google employee.
# Listing either fails honest commits wholesale, so the products that send from them are meant
# to be caught by name in `_PRODUCTS` instead. That leaves a known gap rather than a closed
# one: Gemini has no vendor domain here and only its two long product phrases in `_PRODUCTS`,
# so a trailer naming it any other way is not caught on this surface. Widening this table is a
# decision about false positives, not an oversight to patch.
_VENDOR_DOMAINS = re.compile(
    r"@(?:[\w-]+\.)*(?:anthropic\.com|openai\.com|cursor\.(?:sh|com)|codeium\.com"
    r"|windsurf\.com|mistral\.ai|devin\.ai|aider\.chat)\b",
    re.IGNORECASE,
)
# The name rule: the whole name is a product, not a person. `Claude Lemaire` is a person.
_PRODUCTS = re.compile(
    r"(?:claude code|claude (?:opus|sonnet|haiku)(?: [\w.]+)*|github copilot|copilot"
    r"|cursor agent|openai codex|codex|devin|windsurf|aider|gemini cli|gemini code assist)",
    re.IGNORECASE,
)
# A footer names the vendor as a word, never as a prefix of a package (`openai-python`) or a
# possessive (`openai's`).
_FOOTER = re.compile(
    rf"^[ \t]*(?:\U0001F916[ \t]*)?generated (?:with|by)[ \t]*\[?(?:{_VENDORS})\b(?![-'])",
    re.IGNORECASE,
)
# The marker is the whole line, optionally `by <tool>`; a sentence that starts with the words
# and goes on (`AI-generated summaries are now cached`) is prose.
_MARKER = re.compile(
    r"^[ \t]*(?:\U0001F916[ \t]*)?ai[- ]generated(?:[ \t]+(?:by|with)[ \t]+\S.*)?[ \t]*$",
    re.IGNORECASE,
)


def _trailer_offence(line: str) -> bool:
    match = _TRAILER.match(line)
    if match is None:
        return False
    name, _, address = match.group("value").partition("<")
    if _VENDOR_DOMAINS.search(address):
        return True
    return _PRODUCTS.fullmatch(name.strip()) is not None


_PATTERNS: tuple[tuple[str, Callable[[str], bool]], ...] = (
    ("attribution trailer naming an AI tool", _trailer_offence),
    ("generated-with footer", lambda line: _FOOTER.search(line) is not None),
    ("AI-generated marker line", lambda line: _MARKER.search(line) is not None),
)


class Offence(NamedTuple):
    line: int
    label: str


class Commit(NamedTuple):
    sha: str
    message: str


class Violation(NamedTuple):
    sha: str
    offences: tuple[Offence, ...]


class Report(NamedTuple):
    commits: int
    violations: tuple[Violation, ...]


# A wall-clock bound on one `git log` over a range (D7: a cap, not a config key). Larger than
# `gitenv.GIT_TIMEOUT_SECONDS` because a pull-request range can be hundreds of commits; a
# `git log` that takes longer than this is a repository this command cannot judge in CI.
LOG_TIMEOUT_SECONDS = 60
ATTRIBUTION_LABELS = tuple(label for label, _ in _PATTERNS)


def _final_paragraph_start(lines: list[str]) -> int:
    """Index of the first line of the last paragraph, counting trailing blanks as part of it.

    The scan for the separator begins at the last **non-blank** line, not at the last line. A
    message ending in a blank — or in a whitespace-only line, which no editor renders — would
    otherwise put the separator below every trailer and leave an empty final paragraph, and
    one trailing space would disable the check outright.
    """
    end = len(lines)
    while end > 0 and not lines[end - 1].strip():
        end -= 1
    for index in range(end - 1, -1, -1):
        if not lines[index].strip():
            return index + 1
    return 0


def offending_lines(message: str) -> list[Offence]:
    """`(line number, label)` for every attribution line in `message`'s final paragraph.

    The offending text itself is never carried: a commit message is repository-authored, and
    only what this module computed travels to a summary or a hook's context.
    """
    lines = message.splitlines()
    start = _final_paragraph_start(lines)
    hits: list[Offence] = []
    for number, line in enumerate(lines[start:], start=start + 1):
        for label, matches in _PATTERNS:
            if matches(line):
                hits.append(Offence(number, label))
                break
    return hits


def strip_message(message: str) -> str:
    """Drop the final paragraph's attribution lines and the blank their removal orphans.

    **The body is never rewritten.** Only lines at or after the final paragraph's start are
    removed, and the one line above it this can touch is the blank separator the paragraph's
    removal left dangling at the end of the message — popped with any other trailing blank,
    because a trailing blank is not a body line. A doubled blank inside the body stays doubled:
    normalising blank runs message-wide is what the first cut of this did, and it made the
    docstring's own promise false. A message with no offence is returned byte for byte.
    """
    lines = message.splitlines()
    doomed = {offence.line - 1 for offence in offending_lines(message)}
    if not doomed:
        return message
    start = _final_paragraph_start(lines)
    kept = lines[:start] + [
        line for index, line in enumerate(lines[start:], start=start) if index not in doomed
    ]
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept) + "\n" if kept else ""


def commits_in(root: Path, rev_range: str) -> list[Commit]:
    """`(sha, message)` for each commit in `rev_range`, oldest first.

    `%x00` separates sha from message and `%x01` separates commits: neither can occur in a
    commit message, unlike any printable delimiter. The range is refused when it is shaped
    like an option (§3) and closed with `--` so it can never be read as a pathspec.
    """
    if rev_range.startswith("-"):
        raise Refusal(f"{rev_range!r} looks like an option, not a revision range")
    try:
        # S603/S607: list form, never a shell; `git` through PATH because the machine owner's
        # git must answer (see `gitenv`); the range was checked above and is closed by `--`.
        completed = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "git",
                "-C",
                str(root),
                "log",
                "--reverse",
                "--format=%H%x00%B%x01",
                rev_range,
                "--",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=LOG_TIMEOUT_SECONDS,
            env=scrubbed_env(),
        )
    # None of the three refusals below carries a byte this module did not compute. `git log`'s
    # stderr is repository-authored and unbounded — `warning: ignoring broken ref …`, `error:
    # object file … is empty`, `fatal: bad object <name>` all quote refs and object names — and
    # `TimeoutExpired`/`OSError` stringify the whole argv, `root` included. The range is the
    # caller's own string and is the actionable part; it is the only thing printed.
    except subprocess.TimeoutExpired:
        raise Refusal(
            f"git took longer than {LOG_TIMEOUT_SECONDS}s to read {rev_range!r}"
        ) from None
    except OSError:
        raise Refusal(f"git could not be run to read {rev_range!r}") from None
    if completed.returncode != 0:
        raise Refusal(f"git could not read {rev_range!r}; run it yourself to see why")
    commits: list[Commit] = []
    for raw in completed.stdout.split("\x01"):
        record = raw.strip("\n")
        if not record:
            continue
        sha, _, message = record.partition("\x00")
        commits.append(Commit(sha, message))
    return commits


def check_range(root: Path, rev_range: str, config: Config) -> Report:
    commits = commits_in(root, rev_range)
    violations: list[Violation] = []
    if not config.commit_messages.attribution_check:
        return Report(len(commits), ())
    for sha, message in commits:
        offences = offending_lines(message)
        if offences:
            violations.append(Violation(sha, tuple(offences)))
    return Report(len(commits), tuple(violations))
