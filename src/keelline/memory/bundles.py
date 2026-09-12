"""What each `SessionStart` entry injects, and how much of it fits (§9.5).

One entry per bundle, each rendered by `memory session-context --bundle <name> --part <n>`,
and **no dispatcher handler**. That is not a style choice. Foundation's `hook <event>` takes
an event name and runs every handler registered for it, joining their contexts and clamping
the join to one platform cap — so nine numbered slots registered as handlers would concatenate
back into a single 10,000-character budget and be truncated, which is precisely the defect
§9.5 exists to remove. Invoked as separate `hooks.json` entries, each slot gets its own cap,
and the text is emitted raw rather than through a JSON envelope, so the margin below is
genuinely additive instead of fighting `ensure_ascii`'s six characters per non-ASCII point.

Standing rules are never truncated, only flagged: a standing rule that does not arrive is a
standing rule that gets broken, and the set is hand-curated by a flag, so its size is
somebody's decision rather than an accident.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from keelline.config.schema import Config
from keelline.memory import trust
from keelline.memory.index import INDEX_NAME, is_volatile
from keelline.memory.notes import Note, walk
from keelline.memory.store import Store
from keelline.presets import load_preset


class Bundle(StrEnum):
    PRESET_RULES = "preset-rules"
    STANDING_RULES = "standing-rules"
    VOLATILE_NOTES = "volatile-notes"
    INDEX = "index"


# How many numbered entries `hooks/hooks.json` declares for each bundle. Raising one edits
# that shipped file, which the `hooks-core` lane owns (§9.5); `doctor` compares these against
# what a store actually needs and reports a bundle that does not fit.
SLOTS: dict[Bundle, int] = {
    Bundle.PRESET_RULES: 1,
    Bundle.STANDING_RULES: 3,
    Bundle.VOLATILE_NOTES: 3,
    Bundle.INDEX: 2,
}

# The emitted string is the bundle text plus a trailing newline. The margin covers exactly
# that: not a JSON envelope, since this text is printed raw. Fixed by design, like
# `store._GIT_TIMEOUT_SECONDS` and `trust._NONCE_BYTES` — no shipped config file has any
# business overriding how much room a trailing newline needs.
CAP_MARGIN = 16

STANDING_LEAD = (
    "## Standing rules for this session, injected in full\n\n"
    "These hold for the whole session whatever it turns out to be about, which is exactly why "
    "routing them fails: there is no moment at which you would think to look one up. Each "
    "block below is the note itself, not a summary of it."
)
VOLATILE_LEAD = (
    "## Volatile working memory, injected in full\n\n"
    "Dated, perishable facts about what is currently broken, blocked or half-shipped. They "
    "were true when written: verify any path, flag or date before acting on one, and delete a "
    "note once it is resolved."
)


@dataclass(frozen=True)
class Fit:
    parts: int
    slots: int
    oversized: int

    @property
    def overflow(self) -> int:
        return max(0, self.parts - self.slots)

    @property
    def fits(self) -> bool:
        return self.overflow == 0 and self.oversized == 0


def _cap(config: Config) -> int:
    return max(1, config.native_caps.hook_output_chars - CAP_MARGIN)


def _notes(store: Store, config: Config) -> list[Note]:
    return walk(store.path, [g for g in config.memory.groups if g in store.groups]).notes


def _flag(note: Note, today: date, ttl: int) -> str:
    if note.as_of is None:
        return "  [as_of MISSING — add it or delete the note]"
    age = (today - note.as_of).days
    return f"  [{age} days old — verify or delete before relying on it]" if age > ttl else ""


def _standing(store: Store, config: Config) -> list[str]:
    ranked = [
        note
        for note in _notes(store, config)
        if note.startup is not None and not is_volatile(note.group_name)
    ]
    if not ranked:
        return []
    ranked.sort(key=lambda note: (note.startup or 0, note.name))
    blocks = [STANDING_LEAD] + [f"### {note.name}\n\n{note.body}" for note in ranked]
    total = sum(len(block.split()) for block in blocks)
    budget = config.budgets.effective("startup_rules_words")
    if total > budget:
        blocks.append(
            f"_The standing set has grown to {total} words (> {budget}). Nothing was dropped; "
            "prune the `startup` flags before adding another._"
        )
    return blocks


def _volatile(store: Store, config: Config) -> list[str]:
    notes = [note for note in _notes(store, config) if is_volatile(note.group_name)]
    if not notes:
        return []
    today = date.today()
    ttl = config.budgets.effective("volatile_ttl_days")
    notes.sort(key=lambda note: (note.as_of is not None, note.as_of or date.min), reverse=True)
    notes.sort(key=lambda note: note.as_of is not None)
    full = [
        f"### {note.name}"
        + (f" (as_of {note.as_of})" if note.as_of else "")
        + _flag(note, today, ttl)
        + f"\n\n{note.body}"
        for note in notes
    ]
    if sum(len(block.split()) for block in full) <= config.budgets.effective(
        "volatile_notes_words"
    ):
        return [VOLATILE_LEAD, *full]
    short = "\n".join(
        f"- {note.name}{_flag(note, today, ttl)} — {note.description}" for note in notes
    )
    return [
        VOLATILE_LEAD,
        "Volatile memory has outgrown its budget; listing descriptions only — open any note "
        "that matters:",
        short,
    ]


def _preset_rules(config: Config) -> list[str]:
    # `presets/` belongs to the `setup` lane; foundation wrote only budgets, caps and
    # defaults. Until a `[rules]` table ships, this bundle is silent by design.
    rules = load_preset(config.keelline.preset).get("rules", {})
    if not isinstance(rules, dict) or not rules:
        return []
    return [f"### {name}\n\n{body}" for name, body in rules.items() if isinstance(body, str)]


def _index(store: Store) -> list[str]:
    path = store.path / INDEX_NAME
    if not path.is_file():
        return []
    try:
        return [path.read_text(encoding="utf-8")]
    except OSError:
        return []


def blocks(
    bundle: Bundle, store: Store, config: Config, *, machine: Path | None = None
) -> list[str]:
    if bundle is Bundle.PRESET_RULES:
        # The owner's own rules, from the plugin. Never repository content, so no trust gate.
        return _preset_rules(config)
    if not trust.may_inject(store, config, machine=machine):
        return []
    produced = {
        Bundle.STANDING_RULES: lambda: _standing(store, config),
        Bundle.VOLATILE_NOTES: lambda: _volatile(store, config),
        Bundle.INDEX: lambda: _index(store),
    }[bundle]()
    if not produced or not trust.is_repository_data(store):
        return produced
    nonce = trust.new_nonce()
    return [trust.wrap(block, nonce) for block in produced]


def split(parts: Sequence[str], cap: int) -> list[str]:
    """Pack blocks into parts of at most `cap` characters, truncating none of them."""
    packed: list[str] = []
    current: list[str] = []
    size = 0
    for block in parts:
        length = len(block) + (2 if current else 0)
        if current and size + length > cap:
            packed.append("\n\n".join(current))
            current, size = [], 0
            length = len(block)
        current.append(block)
        size += length
    if current:
        packed.append("\n\n".join(current))
    return packed


def fit(bundle: Bundle, store: Store, config: Config, *, machine: Path | None = None) -> Fit:
    cap = _cap(config)
    parts = split(blocks(bundle, store, config, machine=machine), cap)
    return Fit(
        parts=len(parts),
        slots=SLOTS[bundle],
        oversized=sum(1 for part in parts if len(part) > cap),
    )


def render(
    bundle: Bundle,
    store: Store,
    config: Config,
    *,
    part: int = 1,
    machine: Path | None = None,
) -> str | None:
    parts = split(blocks(bundle, store, config, machine=machine), _cap(config))
    if part < 1 or part > len(parts):
        return None
    return parts[part - 1]
