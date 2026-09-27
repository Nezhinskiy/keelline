"""What every check in the ledger, docs and memory areas returns, and how a summary line
renders a list of them (§5.2: one line per command).

The label carries what this lane computed — a repo-relative path, a line number, a rule name
from this lane's own vocabulary; the detail may quote the repository and is for `--json`
(CONTRIBUTING: repository bytes are data). A leaf module: three areas import it.

**The path is bounded too.** It is a name found on disk, so the repository chose it, and a
tracked file may be called `x\n::error::...` or carry an escape sequence: printed raw, the
first forges a workflow command on a CI runner and the second drives the reader's terminal.
A path inside `PATH_VALUE`, the one grammar a path may print in, prints as itself; any other
prints as `UNPRINTABLE`, and `--json` still carries it, escaped.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from keelline.config.schema import PATH_VALUE

# Items per summary line, capped. A check over a neglected ledger reports findings by the
# hundred and the remediation is one command for the whole set, so the tail is length, not
# information — and printing it pushes the command that repairs the tree off the end of the
# line. One cap for every message rather than a per-call knob, and not a config key (D7): a
# caller free to choose is a caller free to reintroduce the thousands-of-characters summary
# line this exists to prevent.
LISTED_LIMIT = 8
# What a repository-authored path or name outside `PATH_VALUE` prints as. Fixed text, and it
# says where the name itself went.
UNPRINTABLE = "<unprintable name; see --json>"


def printable(path: str) -> str:
    """The path as a printed line may carry it: itself inside the path grammar, `UNPRINTABLE`
    outside."""
    return path if PATH_VALUE.match(path) else UNPRINTABLE


def quoted(path: str) -> str:
    """The path as a refusal may carry it: itself inside the path grammar, its `repr` outside.

    For a message with no `--json` payload behind it, where withholding the name would leave
    the operator nothing to rename: `repr` escapes every line break and control character, so
    the name arrives whole and cannot start a line or drive a terminal."""
    return path if PATH_VALUE.match(path) else repr(path)


class Severity(StrEnum):
    """How much a finding asks of the person reading it: a warning is worth acting on now, and
    advice is worth reading. The one scale, so a profile's check and an assessment item cannot
    grade on two."""

    ADVICE = "advice"
    WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str  # repo-relative or store-relative; "" for a finding about the tree as a whole
    line: int | None
    detail: str  # may quote the repository; `--json` only

    @property
    def label(self) -> str:
        where = printable(self.path) if self.path else "-"
        if self.line is not None:
            where = f"{where}:{self.line}"
        return f"{where} [{self.rule}]"


def listed(items: list[str]) -> str:
    if len(items) <= LISTED_LIMIT:
        return ", ".join(items)
    return f"{', '.join(items[:LISTED_LIMIT])}, and {len(items) - LISTED_LIMIT} more"


def labels(findings: list[Finding]) -> str:
    return listed([finding.label for finding in findings])
