"""What a sweep reads (§5.2's `memory inventory`).

`--json` is the primary output: the `memory-sweep` skill consumes this, and the human
rendering is a convenience. Staleness applies only to the volatile group — a durable note has
no expiry, and flagging one teaches the reader to ignore the flag.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from keelline.config.schema import Config
from keelline.memory.index import Reconciliation, is_volatile
from keelline.memory.notes import Provenance


@dataclass(frozen=True)
class Entry:
    name: str
    group: str
    words: int
    type: str | None
    startup: int | None
    as_of: str | None
    stale: bool
    provenance: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def inventory(reconciled: Reconciliation, config: Config) -> list[Entry]:
    today = date.today()
    ttl = config.budgets.effective("volatile_ttl_days")
    entries = [
        Entry(
            name=note.name,
            group=note.group_name,
            words=note.words,
            type=note.type.value if note.type else None,
            startup=note.startup,
            as_of=note.as_of.isoformat() if note.as_of else None,
            stale=(
                is_volatile(note.group_name)
                and (note.as_of is None or (today - note.as_of).days > ttl)
            ),
            provenance=note.index_provenance.value,
        )
        for note in reconciled.notes
    ]
    entries.sort(key=lambda entry: (-entry.words, entry.name))
    return entries


def totals(entries: list[Entry], config: Config) -> dict[str, int]:
    del config
    return {
        "notes": len(entries),
        "words": sum(entry.words for entry in entries),
        "provisional": sum(1 for e in entries if e.provenance == Provenance.PROVISIONAL.value),
        "stale": sum(1 for entry in entries if entry.stale),
        "undated": sum(1 for e in entries if is_volatile(e.group) and e.as_of is None),
        # The same two conditions `bundles._standing` selects on, and for the same reason: a
        # volatile note is a dated, perishable fact, so it is injected by the volatile bundle
        # whatever `startup` it carries. Counting every flagged note made this headline number
        # disagree with what actually reaches the model — and this number is what the
        # `memory-sweep` skill reads and quotes.
        "standing": sum(1 for e in entries if e.startup is not None and not is_volatile(e.group)),
    }
