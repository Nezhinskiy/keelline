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

**Only the trailing attribution block is judged**, and that is this port's one deliberate
divergence. Git trailers and harness footers are appended at the end of a message, so the end
is the only place a real attribution can appear; everything above it is prose, and a repository
that uses coding agents writes that prose constantly — provider names, model ids, paths, and
quoted trailers in a message about this very policy. Judging the whole message let ``strip``
amputate a body sentence, which is the worse failure of the two: the range check still catches
a trailer the hook left behind, but nothing puts a deleted sentence back.

The block is the last paragraph, plus each paragraph above it whose every line is itself an
attribution line. The walk stops dead at the first paragraph carrying any line that is not.
**One paragraph was not enough**, and that is measured rather than foreseen: the canonical
harness attribution is *two* paragraphs — a ``Generated with`` footer, a blank line, then a
``Co-Authored-By:`` trailer — so judging only the last of them removed the trailer and left
the footer. The hook printed a successful strip, the range check then failed the same commit
in CI naming one of the two offences, and fixing the one it named failed again on the next
run.

**What the walk costs, stated rather than implied.** A paragraph of prose is safe because prose
does not match; a paragraph is *not* safe merely because it is body text. Anything the rules
below call an attribution is judged as one wherever the walk reaches it — and the walk reaches
**every** paragraph in the run above the block whose lines all match, not only the one directly
above it, and a paragraph of several quoted trailers as readily as a single line. A message
that pastes forbidden trailers as examples, in as many paragraphs as it likes, loses all of
them, ``commit strip`` doing the removing before the commit exists. The protection this keeps
is the one that matters and the one the paragraph rule was for: the walk cannot step *over* a
paragraph, so one non-matching line anywhere in a paragraph makes that paragraph and everything
above it unreachable, and a body paragraph at the end of the message stops the walk before it
starts.

**Trailing blank lines are not the final paragraph.** The search for the paragraph separator
starts at the last *non-blank* line, because otherwise a message ending in a blank — or in a
line of nothing but spaces, which no editor shows — leaves an empty final paragraph, and a gate
whose whole point is that it cannot be bypassed is bypassed by one trailing space. That is a
measured defect of the first cut of this module, not a hypothetical.

The trailer rule reads the trailer's *value*, not the whole line: an address at a vendor's own
mail domain, or a whole name that is a product phrase. **A value that continues into a WORD
past its address is a sentence, not a trailer.** Without that test everything past the ``>`` is
discarded as part of the address and an English sentence built on a trailer key reads as a bare
trailer — measured, ``Reviewed-by: Copilot <x@y.z> said nothing useful.`` was flagged, and
under the paragraph walk above it was stripped as well.

The exact shape of that test is load-bearing, and both tempting simplifications of it were
measured **missing a real trailer**, which is the expensive direction. "The value must end at
``>``" loses an unterminated one (``<noreply@anthropic.com``, closing bracket knocked off),
which carries no ``>`` at all. "Anything after ``>`` is prose" loses a trailer with ordinary
trailing punctuation — ``Co-Authored-By: Claude <noreply@anthropic.com>.`` is the canonical
harness trailer plus one typed full stop, and a gate that a full stop bypasses is not a gate.
So: a word character in the tail after the **last** ``>``, the last rather than the first
because a display name may carry brackets of its own (``Claude <bot> <address>``) and splitting
at the first one reads the real address as prose. Prose that happens to end in ``>`` is flagged
rather than missed, which is the cheap direction.

**The domain rule's cost is chosen, not overlooked** — a person whose employer is a vendor
(``alice@openai.com``) is indistinguishable from that vendor's bot by address alone, and is
flagged. Dropping the domain rule to spare them would miss every bot whose trailer name is not
a product phrase, which is most of them.

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

One consequence worth knowing, and it is larger than a failed check. A commit message that
quotes a forbidden trailer or footer as an example — plausible when editing this policy — is
judged wherever the walk reaches it: not only in the closing paragraph but in every paragraph
above it that is nothing *but* such quoted lines. ``commit check`` fails on it, and ``commit
strip`` removes those lines from the message before the commit exists, silently apart from
its count. Describe the trailer instead of pasting it, or keep a sentence of your own prose in
the same paragraph — a paragraph with one non-matching line in it ends the walk and is never
read.
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
# Tested-by are all used by agent harnesses; the value is what decides, and `_trailer_offence`
# requires it to end at its address. A value folded onto a continuation line is read to the end
# of the first line only (see the docstring).
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
# What tells a trailer's trailing punctuation from a sentence continuing past the address: one
# word character. `\w` and not `[A-Za-z]` on purpose — a tail is prose in any script, and
# `str.isalnum`-style breadth is what keeps this from being an English-only rule.
_WORD = re.compile(r"\w")


def _trailer_offence(line: str) -> bool:
    match = _TRAILER.match(line)
    if match is None:
        return False
    name, _, address = match.group("value").partition("<")
    # A trailer's value ends at its address; a value that CONTINUES INTO A WORD past the
    # address is a sentence. Without this, everything after the `>` lands in the discarded
    # "address" half, so `Reviewed-by: Copilot <x@y.z> said nothing useful.` -- this module's
    # own designated example of trailer-shaped prose -- read as a bare `Copilot` trailer.
    #
    # Two spellings were measured and rejected, both of which MISS A REAL TRAILER, which is
    # the expensive direction here and the reason this reads the way it does:
    #
    # * "the value must end at `>`" loses an unterminated trailer
    #   (`<noreply@anthropic.com`, closing bracket knocked off) -- it carries no `>` at all.
    # * "anything at all after `>` is prose" loses a trailer with ordinary trailing
    #   punctuation: a full stop, a comma, a semicolon, a closing paren, an em dash, an
    #   ellipsis. `Co-Authored-By: Claude <noreply@anthropic.com>.` is the canonical trailer
    #   with one typed character, and missing it is a bypass.
    #
    # So the test is a WORD CHARACTER after the address, and it is taken after the LAST `>`
    # rather than the first: a display name that itself carries brackets
    # (`Claude <bot> <noreply@anthropic.com>`) puts a real address after an inner `>`, and
    # splitting at the first one reads the real trailer as prose. A prose line that happens to
    # END in `>` is flagged instead -- a false positive, which is the cheap direction.
    _, bracket, tail = address.rpartition(">")
    if bracket and _WORD.search(tail):
        return False
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


def _final_paragraph_start(lines: list[str], end: int | None = None) -> int:
    """Index of the first line of the last paragraph of `lines[:end]`, blanks included in it.

    The scan for the separator begins at the last **non-blank** line, not at the last line. A
    message ending in a blank — or in a whitespace-only line, which no editor renders — would
    otherwise put the separator below every trailer and leave an empty final paragraph, and
    one trailing space would disable the check outright.

    `end` exists so `_attribution_block_start` can ask the same question of the text above a
    paragraph it has already judged; the default is the whole message.
    """
    end = len(lines) if end is None else end
    while end > 0 and not lines[end - 1].strip():
        end -= 1
    for index in range(end - 1, -1, -1):
        if not lines[index].strip():
            return index + 1
    return 0


def _is_attribution(line: str) -> bool:
    return any(matches(line) for _, matches in _PATTERNS)


def _paragraph_is_all_attribution(lines: list[str], start: int, end: int) -> bool:
    """True when `lines[start:end]` has content and every non-blank line of it is attribution.

    Blank lines do not vote: the slice carries the separator below the paragraph, and a
    message's trailing blanks ride on the last one. An empty or all-blank slice is *not* all
    attribution — otherwise the walk would step through it into the body.
    """
    content = [line for line in lines[start:end] if line.strip()]
    return bool(content) and all(_is_attribution(line) for line in content)


def _attribution_block_start(lines: list[str]) -> int:
    """Index of the first line judged: the last paragraph, plus wholly-attribution ones above.

    The canonical harness attribution is two paragraphs, so stopping at the last one left the
    footer behind (see the module docstring). This walks upwards **only while the paragraph it
    reaches is attribution to the last line**, so the first paragraph holding any body line
    ends the walk and nothing above it is ever read — which is what keeps `strip_message` from
    amputating a sentence.
    """
    start = _final_paragraph_start(lines)
    if not _paragraph_is_all_attribution(lines, start, len(lines)):
        return start
    while start > 0:
        earlier = _final_paragraph_start(lines, start)
        if not _paragraph_is_all_attribution(lines, earlier, start):
            break
        start = earlier
    return start


def offending_lines(message: str) -> list[Offence]:
    """`(line number, label)` for every attribution line in `message`'s attribution block.

    The offending text itself is never carried: a commit message is repository-authored, and
    only what this module computed travels to a summary or a hook's context.
    """
    lines = message.splitlines()
    start = _attribution_block_start(lines)
    hits: list[Offence] = []
    for number, line in enumerate(lines[start:], start=start + 1):
        for label, matches in _PATTERNS:
            if matches(line):
                hits.append(Offence(number, label))
                break
    return hits


def strip_message(message: str) -> str:
    """Drop the attribution block's attribution lines and the blank their removal orphans.

    **The body is never rewritten.** Only lines at or after the block's start are removed, and
    the one line above it this can touch is the blank separator the removal left dangling at
    the end of the message — popped with any other trailing blank, because a trailing blank is
    not a body line. A doubled blank inside the body stays doubled: normalising blank runs
    message-wide is what the first cut of this did, and it made the docstring's own promise
    false. A message with no offence is returned byte for byte.
    """
    lines = message.splitlines()
    doomed = {offence.line - 1 for offence in offending_lines(message)}
    if not doomed:
        return message
    start = _attribution_block_start(lines)
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
    """Judge every message in `rev_range`, unless `attribution_check` switches the rules off.

    The log runs either way, and that is the contract rather than an oversight: with the flag
    false the report still says how many messages it read, and nothing but `git log` can
    answer that. So the flag stops a message ever *being* a violation; it does not make an
    unreadable range readable, and such a range is still a refusal.
    """
    commits = commits_in(root, rev_range)
    violations: list[Violation] = []
    if not config.commit_messages.attribution_check:
        return Report(len(commits), ())
    for sha, message in commits:
        offences = offending_lines(message)
        if offences:
            violations.append(Violation(sha, tuple(offences)))
    return Report(len(commits), tuple(violations))
