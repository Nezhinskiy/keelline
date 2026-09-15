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
from keelline.memory.index import index_source, is_volatile
from keelline.memory.notes import Note, walk
from keelline.memory.store import Store, in_repository
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
    # Three, and the arithmetic is the reason. `memory_index_bytes` is 25600 and a part holds
    # `hook_output_chars - CAP_MARGIN` = 9984, so an index written right up to its own
    # configured cap needs three parts and two could never hold it. It was two, and worse, the
    # second was unreachable: `_index` returned the whole file as one block and `split` never
    # breaks a block, so a 22,816-byte index — under every configured cap — packed into one
    # part of 23,126 characters that the harness truncated at 10,000, with part 2 empty and
    # `keelline memory index` exiting 0 saying "index is current".
    Bundle.INDEX: 3,
}

# How much of `native_caps.hook_output_chars` this lane keeps back. `_cap` subtracts it, so a
# part packed to `_cap` and emitted raw is the bundle plus one trailing newline: measured at
# `hook_output_chars = 10000`, 9,985 characters emitted with 15 to spare.
#
# **D7, stated as the deviation it is.** The Global Constraint asks for a budget, a cap or a
# TTL to come from `config.budgets`, `config.native_caps`, or a named module constant *whose
# comment says which shipped file must change with it*. There is no such file for this one and
# there should not be: it is the headroom between a cap this lane does not own and the way this
# lane emits text, and a project that could widen it would be a project that could make its own
# bundles overrun the platform truncation silently. So this names no shipped file, which is a
# departure from the constraint's literal wording rather than a satisfaction of it — the same
# departure `store._GIT_TIMEOUT_SECONDS` and `trust._NONCE_BYTES` make, and it is flagged here
# rather than dressed up as compliance. The cap it is subtracted from, `hook_output_chars`, is
# where D7 is actually satisfied.
#
# **For the `hooks-core` lane, which reads `SLOTS` out of this file: the `hooks.json` entries
# must not pass `--json`.** The margin is additive only because `memory session-context` prints
# the text raw. Through `cli._emit`'s `json.dumps({"summary": ...}, indent=2)` the envelope and
# the escaping both count against the same platform cap, and a cap-length standing bundle no
# longer fits — measured at 10,009 characters for the single-block bundle
# `test_the_margin_is_additive_because_the_text_is_emitted_raw` builds, and 10,146 for a
# realistic multi-note one, whose extra newlines each escape to two characters. Widening
# `CAP_MARGIN` is not the fix; not wrapping the output is.
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
    # Undated notes first — an `as_of` a writer never added is the one that most needs looking
    # at — then the dated ones, newest first.
    #
    # One sort, where there were two. The second sorted on `as_of is not None`, which is
    # *exactly* the first element of the first sort's key, so that element decided nothing: the
    # second pass re-partitioned on the same predicate and only the date ordering inside each
    # partition survived. Verified over 2,000 random orderings that the one key below is
    # identical to the pair. Writing it as one sort is also what makes the ordering readable —
    # "undated first, then newest first" is not a claim anybody could check against two
    # `reverse=True` passes that partly undo each other.
    notes.sort(key=lambda note: (note.as_of is not None, -(note.as_of or date.min).toordinal()))
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


# Where `_index` is allowed to break the index into blocks: the start of a `## ` section, which
# is the same boundary `index.render_index` builds it on. `split` packs blocks and never breaks
# one, so a bundle that returns a single block can only ever fill a single slot however many
# the platform gives it — the mistake the `INDEX: 3` comment above describes.
_SECTION = "\n## "


def _index(source: Path | None) -> list[str]:
    """The index, once `index.index_source` has said which file the index actually is.

    Reading `store.path / INDEX_NAME` directly was the defect: `is_file()` follows symlinks and
    nothing asked where the link went, while `worktree.link` already applied §9.1's per-link
    target rule to the very same file. This is the path that reaches the model, so it gets the
    rule first, not last.

    Returned as one block per section rather than as the whole file, so `split` has something
    to pack. The header and every section keep their own text exactly; only the joins between
    them are re-made, and `split` re-makes them as the blank line `render_index` already writes.
    A section that is on its own larger than one part is still one block — the honest answer is
    that it does not fit, which `Fit.oversized` reports and `doctor` reads, rather than a cut
    made at whatever character the budget ran out on.
    """
    if source is None or not source.is_file():
        return []
    try:
        text = source.read_text(encoding="utf-8")
    except OSError:
        return []
    if not text.strip():
        return []
    head, *sections = text.split(_SECTION)
    blocks = [head.rstrip("\n"), *(f"## {section}".rstrip("\n") for section in sections)]
    return [block for block in blocks if block.strip()]


def blocks(bundle: Bundle, store: Store, config: Config) -> list[str]:
    if bundle is Bundle.PRESET_RULES:
        # The owner's own rules, from the plugin. Never repository content, so no trust gate.
        return _preset_rules(config)
    # The index is asked about by file, not by store. `trust.inside_project` inspects
    # `store.groups`, and in overlay mode every group resolves into the overlay while
    # `store.path` is a real directory *in the repository* — so a committed `MEMORY.md` sitting
    # there used to reach the model with `may_inject` returning True on no trust record and
    # `is_repository_data` returning False, unwrapped. Where the file itself sits is the
    # question, and `in_repository` is the one that asks it.
    source = index_source(store, config) if bundle is Bundle.INDEX else None
    from_repository = trust.is_repository_data(store) or (
        source is not None and in_repository(store, source)
    )
    if not trust.may_inject(store, config, repository_data=from_repository):
        return []
    produced = {
        Bundle.STANDING_RULES: lambda: _standing(store, config),
        Bundle.VOLATILE_NOTES: lambda: _volatile(store, config),
        Bundle.INDEX: lambda: _index(source),
    }[bundle]()
    if not produced or not from_repository:
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


def fit(bundle: Bundle, store: Store, config: Config) -> Fit:
    cap = _cap(config)
    parts = split(blocks(bundle, store, config), cap)
    return Fit(
        parts=len(parts),
        slots=SLOTS[bundle],
        oversized=sum(1 for part in parts if len(part) > cap),
    )


# What an oversized part is replaced with. Keelline's own words and two values Keelline chose —
# the bundle name and the slot number — so nothing repository-authored rides out through a
# channel that has just been established not to be able to carry it safely.
OVERSIZED_NOTICE = (
    "keelline: the {bundle} bundle's part {part} is a single block larger than one "
    "session-start slot, so it was withheld rather than delivered cut in half. Nothing here is "
    "missing from the store; run `keelline memory fit` to see which block is oversized, and "
    "split or shorten it."
)


def render(bundle: Bundle, store: Store, config: Config, *, part: int = 1) -> str | None:
    """One numbered slot's text, or `None` when there is no such part.

    **An oversized part is a notice, not the part.** `split` never breaks a block, so a single
    block larger than the cap becomes a part larger than the cap — `fit` reports that as
    `Fit.oversized`, and `render` used to hand it out anyway and exit 0. Nothing on the hook
    path runs `fit`, so the only reader was `doctor`, and what actually happened was that the
    platform truncated it. Measured, at `hook_output_chars = 10000`: a standing bundle with one
    20,288-character part arrived with **one** of its two region markers — the model got an
    opening delimiter, the lead sentence "It ends at the matching end marker and nowhere else",
    and no end marker, which is the one thing `trust.wrap`'s nonce region exists to make
    impossible. Handing out a region known to arrive unterminated is worse than handing out
    nothing, and saying so is better than either.

    The notice carries no repository content — the bundle name and the slot number are
    Keelline's own — for the obvious reason that the channel has just been established not to
    be able to carry any safely. It is emitted whatever the configured cap, because a truncated
    notice still reads as a notice while a truncated region does not.
    """
    cap = _cap(config)
    parts = split(blocks(bundle, store, config), cap)
    if part < 1 or part > len(parts):
        return None
    text = parts[part - 1]
    if len(text) > cap:
        return OVERSIZED_NOTICE.format(bundle=bundle.value, part=part)
    return text
