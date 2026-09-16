"""What every check in the ledger, docs and memory areas returns, and how a summary line
renders a list of them (§5.2: one line per command).

The label carries what this lane computed — a repo-relative path, a line number, a rule name
from this lane's own vocabulary; the detail may quote the repository and is for `--json`
(CONTRIBUTING: repository bytes are data). A leaf module: three areas import it.
"""

from __future__ import annotations

from dataclasses import dataclass

# Items per summary line, capped. A check over a neglected ledger reports findings by the
# hundred and the remediation is one command for the whole set, so the tail is length, not
# information — and printing it pushes the command that repairs the tree off the end of the
# line. One cap for every message rather than a per-call knob, and not a config key (D7): a
# caller free to choose is a caller free to reintroduce the thousands-of-characters summary
# line this exists to prevent.
LISTED_LIMIT = 8


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str  # repo-relative or store-relative; "" for a finding about the tree as a whole
    line: int | None
    detail: str  # may quote the repository; `--json` only

    @property
    def label(self) -> str:
        where = self.path or "-"
        if self.line is not None:
            where = f"{where}:{self.line}"
        return f"{where} [{self.rule}]"


def listed(items: list[str]) -> str:
    if len(items) <= LISTED_LIMIT:
        return ", ".join(items)
    return f"{', '.join(items[:LISTED_LIMIT])}, and {len(items) - LISTED_LIMIT} more"


def labels(findings: list[Finding]) -> str:
    return listed([finding.label for finding in findings])
