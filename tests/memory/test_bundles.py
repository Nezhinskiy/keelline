from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from keelline.config.loader import CONFIG_FILE, load
from keelline.config.schema import Config
from keelline.memory.bundles import CAP_MARGIN, SLOTS, Bundle, blocks, fit, render, split
from keelline.memory.store import Store
from keelline.memory.trust import DELIMITER, record

CONFIG = """
[keelline]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"

[memory]
mode = "{mode}"
groups = ["developer", "project-volatile"]
index_extra = []

[budgets]
startup_rules_words = {startup_words}
volatile_notes_words = {volatile_words}
volatile_ttl_days = 30
"""

GROUPS = ("developer", "project-volatile")


def note(name: str, *, startup: str = "", as_of: str = "", body: str = "Body.") -> str:
    meta = ["metadata:", "  type: project"]
    if startup:
        meta.append(f"  startup: {startup}")
    if as_of:
        meta.append(f"  as_of: {as_of}")
    head = [f"name: {name}", f'description: "{name} description"', f'index: "t → {name}"']
    return "---\n" + "\n".join([*head, *meta]) + "\n---\n\n" + body + "\n"


def a_store(
    tmp_path: Path,
    *,
    mode: str = "overlay",
    startup_words: int = 1600,
    volatile_words: int = 2500,
) -> tuple[Store, Config]:
    root = tmp_path / "project"
    base = (tmp_path / "overlay" / "memory") if mode == "overlay" else (root / "docs" / "memory")
    for group in GROUPS:
        (base / group).mkdir(parents=True)
    (base / "developer" / "second.md").write_text(note("second", startup="5"), encoding="utf-8")
    (base / "developer" / "first.md").write_text(note("first", startup="1"), encoding="utf-8")
    (base / "developer" / "plain.md").write_text(note("plain"), encoding="utf-8")
    fresh = date.today().isoformat()
    stale = (date.today() - timedelta(days=90)).isoformat()
    (base / "project-volatile" / "fresh.md").write_text(
        note("fresh", as_of=fresh), encoding="utf-8"
    )
    (base / "project-volatile" / "stale.md").write_text(
        note("stale", as_of=stale), encoding="utf-8"
    )
    (base / "project-volatile" / "undated.md").write_text(note("undated"), encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    (root / CONFIG_FILE).write_text(
        CONFIG.format(mode=mode, startup_words=startup_words, volatile_words=volatile_words),
        encoding="utf-8",
    )
    config = load(root, machine=tmp_path / "absent.toml")
    store = Store(base, mode, root, {g: base / g for g in GROUPS})
    return store, config


def a_machine(tmp_path: Path) -> Path:
    path = tmp_path / "machine.toml"
    path.write_text("", encoding="utf-8")
    return path


def test_standing_rules_are_ordered_by_rank_and_exclude_unflagged_notes(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    text = "\n".join(blocks(Bundle.STANDING_RULES, store, config))
    assert text.index("first") < text.index("second")
    assert "plain" not in text


def test_standing_rules_are_never_truncated_only_flagged(tmp_path: Path) -> None:
    store, config = a_store(tmp_path, startup_words=1)
    text = "\n".join(blocks(Bundle.STANDING_RULES, store, config))
    assert "first" in text and "second" in text
    assert "has grown" in text


def test_a_volatile_note_is_not_a_standing_rule_even_when_it_is_flagged(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    (store.groups["project-volatile"] / "loud.md").write_text(
        note("loud", startup="-100"), encoding="utf-8"
    )
    assert "loud" not in "\n".join(blocks(Bundle.STANDING_RULES, store, config))


def test_volatile_notes_flag_a_missing_and_a_stale_as_of(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    text = "\n".join(blocks(Bundle.VOLATILE_NOTES, store, config))
    assert "as_of MISSING" in text
    assert "days old" in text
    assert text.index("undated") < text.index("fresh")


def test_volatile_notes_degrade_to_one_line_each_over_budget(tmp_path: Path) -> None:
    store, config = a_store(tmp_path, volatile_words=1)
    text = "\n".join(blocks(Bundle.VOLATILE_NOTES, store, config))
    assert "description" in text
    assert "Body." not in text


def test_preset_rules_emit_nothing_while_the_preset_has_none(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    assert blocks(Bundle.PRESET_RULES, store, config) == []


def test_notes_that_live_in_the_repository_inject_nothing_before_trust(tmp_path: Path) -> None:
    store, config = a_store(tmp_path, mode="local-only")
    machine = a_machine(tmp_path)
    assert blocks(Bundle.STANDING_RULES, store, config, machine=machine) == []
    record(store, config, machine=machine)
    produced = blocks(Bundle.STANDING_RULES, store, config, machine=machine)
    assert produced != []
    assert all(block.startswith(DELIMITER) for block in produced)


def test_the_owners_own_preset_rules_need_no_trust(tmp_path: Path) -> None:
    # A preset ships with the plugin; it is never repository content, so gating it on a
    # repository's trust record would make the owner's own rules hostage to a clone.
    store, config = a_store(tmp_path, mode="local-only")
    assert blocks(Bundle.PRESET_RULES, store, config, machine=a_machine(tmp_path)) == []


def test_an_overlay_store_is_not_wrapped_as_repository_data(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    produced = blocks(Bundle.STANDING_RULES, store, config, machine=a_machine(tmp_path))
    assert produced != []
    assert not any(DELIMITER in block for block in produced)


def test_split_packs_blocks_without_truncating_any() -> None:
    parts = split(["a" * 40, "b" * 40, "c" * 40], cap=100)
    assert len(parts) == 2
    assert "".join(parts).count("a") == 40
    assert "".join(parts).count("c") == 40


def test_a_block_longer_than_the_cap_becomes_its_own_part() -> None:
    parts = split(["a" * 200, "b"], cap=100)
    assert parts[0] == "a" * 200
    assert parts[1] == "b"


def test_render_returns_none_for_a_slot_the_split_did_not_reach(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    assert render(Bundle.STANDING_RULES, store, config, part=1) is not None
    assert render(Bundle.STANDING_RULES, store, config, part=SLOTS[Bundle.STANDING_RULES]) is None


def test_every_part_fits_the_platform_cap_as_it_will_be_emitted(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    for index in range(1, SLOTS[Bundle.STANDING_RULES] + 1):
        text = render(Bundle.STANDING_RULES, store, config, part=index)
        if text is None:
            continue
        # What the command prints is the text plus a newline; no JSON envelope widens it.
        assert len(text) + 1 <= config.native_caps.hook_output_chars


def test_fit_reports_overflow_and_an_oversized_part_separately(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    assert fit(Bundle.STANDING_RULES, store, config).fits is True
    (store.groups["developer"] / "huge.md").write_text(
        note("huge", startup="9", body="word " * 30_000), encoding="utf-8"
    )
    report = fit(Bundle.STANDING_RULES, store, config)
    assert report.oversized == 1
    assert report.fits is False


def test_many_standing_rules_overflow_the_declared_slots(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    for index in range(40):
        (store.groups["developer"] / f"r{index:02d}.md").write_text(
            note(f"r{index:02d}", startup=str(index), body="word " * 400), encoding="utf-8"
        )
    report = fit(Bundle.STANDING_RULES, store, config)
    assert report.parts > report.slots
    assert report.overflow > 0


@pytest.mark.parametrize("bundle", list(Bundle))
def test_every_bundle_has_a_declared_slot_count(bundle: Bundle) -> None:
    assert SLOTS[bundle] >= 1


def test_the_margin_is_additive_because_the_text_is_emitted_raw() -> None:
    assert 0 < CAP_MARGIN < 100
