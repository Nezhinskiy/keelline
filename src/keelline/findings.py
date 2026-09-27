"""What every check in the ledger, docs and memory areas returns, and how a summary line
renders a list of them (one line per command).

The label carries what this lane computed — a repo-relative path, a line number, a rule name
from this lane's own vocabulary; the detail may quote the repository and is for `--json`
(CONTRIBUTING: repository bytes are data). The assess, docs, doctor, guards, ledger and memory
areas import it, and so does `profiles`.

**The path is bounded too.** It is a name found on disk, so the repository chose it, and the
label goes through `printed.printable`: a path inside the path grammar prints as itself, any
other as `UNPRINTABLE`, and `--json` still carries it, escaped. A caller whose output has no
`--json` behind it names its own stand-in through `labelled`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from keelline.printed import UNPRINTABLE, printable

# Items per summary line, capped. A check over a neglected ledger reports findings by the
# hundred and the remediation is one command for the whole set, so the tail is length, not
# information — and printing it pushes the command that repairs the tree off the end of the
# line. One cap for every message rather than a per-call knob, and not a config key: a
# caller free to choose is a caller free to reintroduce the thousands-of-characters summary
# line this exists to prevent.
LISTED_LIMIT = 8


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
        return self.labelled(UNPRINTABLE)

    def labelled(self, withheld: str) -> str:
        """The label with `withheld` standing in for a path outside the path grammar."""
        where = printable(self.path, withheld) if self.path else "-"
        if self.line is not None:
            where = f"{where}:{self.line}"
        return f"{where} [{self.rule}]"


def listed(items: list[str]) -> str:
    if len(items) <= LISTED_LIMIT:
        return ", ".join(items)
    return f"{', '.join(items[:LISTED_LIMIT])}, and {len(items) - LISTED_LIMIT} more"


def labels(findings: list[Finding]) -> str:
    return listed([finding.label for finding in findings])
