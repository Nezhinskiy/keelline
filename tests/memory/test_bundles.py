from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

from keelline.config.loader import CONFIG_FILE, load
from keelline.config.schema import Config
from keelline.memory import bundles as bundles_module
from keelline.memory.bundles import (
    CAP_MARGIN,
    SLOTS,
    STANDING_LEAD,
    Bundle,
    blocks,
    fit,
    render,
    split,
)
from keelline.memory.index import INDEX_NAME
from keelline.memory.store import Store, resolve
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
    # A machine file of this test's own. Without one the store carries `machine=None`, and
    # `may_inject` would consult the developer's real `~/.config/keelline/trust.json`.
    store = Store(base, mode, root, {g: base / g for g in GROUPS}, machine=a_machine(tmp_path))
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
    # Undated-first only pins one boundary; recency within the dated group is a separate
    # claim. Reversing the dated-group sort would leave the line above untouched.
    assert text.index("fresh") < text.index("stale")


def test_volatile_notes_degrade_to_one_line_each_over_budget(tmp_path: Path) -> None:
    store, config = a_store(tmp_path, volatile_words=1)
    text = "\n".join(blocks(Bundle.VOLATILE_NOTES, store, config))
    assert "description" in text
    assert "Body." not in text


def test_the_index_bundle_returns_the_rendered_index_file(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    content = "# Memory Index\n\nA line only this test wrote, not a literal the code repeats.\n"
    (store.path / INDEX_NAME).write_text(content, encoding="utf-8")
    assert blocks(Bundle.INDEX, store, config) == [content.rstrip("\n")]


def test_the_index_bundle_is_empty_when_no_index_file_exists(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    assert not (store.path / INDEX_NAME).exists()
    assert blocks(Bundle.INDEX, store, config) == []


RULES = (
    "decision-forks",
    "worktree-by-default",
    "research-freshness",
    "ci-after-push",
    "language-by-audience",
)
# A rule body with fewer words than this is a stub rather than a rule.
MIN_RULE_BODY_WORDS = 20


def test_the_shipped_preset_rules_render_in_table_order(tmp_path: Path) -> None:
    # The preset is the plugin's, so this reads the real one: a rule dropped from the table,
    # renamed, or reordered reddens here. Mutation: swap the first two tables in
    # `recommended.toml` → reddens on order; delete `ci-after-push` → reddens on length.
    store, config = a_store(tmp_path)
    produced = blocks(Bundle.PRESET_RULES, store, config)
    assert [block.split("\n", 1)[0] for block in produced] == [f"### {name}" for name in RULES]
    # Every rule has a body of at least one sentence; a heading with nothing under it is a
    # rule nobody wrote.
    assert all(len(block.split("\n\n", 1)[1].split()) >= MIN_RULE_BODY_WORDS for block in produced)


def test_the_shipped_preset_rules_fit_one_hook_slot(tmp_path: Path) -> None:
    # A bundle that needs two parts is not wrong, but it is a change the hooks file has to
    # know about (`SLOTS`), so a growing table reddens here before it silently spills.
    # Mutation, run 2026-09-17: pad one rule body in the shipped preset with 8,940 characters
    # of prose. The bundle spilled and this reddened with `assert 2 == 1`, then went green
    # again when the padding came out. The five rules render from about 3.1 KB of body today
    # against a slot of `hook_output_chars - CAP_MARGIN`, so this is a tripwire with room in
    # front of it, not a bound anything sits against.
    store, config = a_store(tmp_path)
    produced = blocks(Bundle.PRESET_RULES, store, config)
    assert len(split(produced, cap=config.native_caps.hook_output_chars - CAP_MARGIN)) == 1


def test_preset_rules_emit_nothing_when_a_preset_has_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The silent case the shipped preset no longer exercises, kept on a fixture: a preset
    # without the table renders nothing rather than a heading over nothing.
    monkeypatch.setattr(bundles_module, "load_preset", lambda name: {"budgets": {}})
    store, config = a_store(tmp_path)
    assert blocks(Bundle.PRESET_RULES, store, config) == []


def test_notes_that_live_in_the_repository_inject_nothing_before_trust(tmp_path: Path) -> None:
    store, config = a_store(tmp_path, mode="local-only")
    assert blocks(Bundle.STANDING_RULES, store, config) == []
    record(store, config)
    produced = blocks(Bundle.STANDING_RULES, store, config)
    assert produced != []
    assert all(block.startswith(DELIMITER) for block in produced)


def test_the_owners_own_preset_rules_need_no_trust(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A preset ships with the plugin; it is never repository content, so gating it on a
    # repository's trust record would make the owner's own rules hostage to a clone. That is
    # supplying a fixture for the `load_preset` collaborator the `setup` lane owns, not
    # mocking the unit under test.
    monkeypatch.setattr(
        bundles_module, "load_preset", lambda name: {"rules": {"greeting": "Hello."}}
    )
    store, config = a_store(tmp_path, mode="local-only")
    assert blocks(Bundle.PRESET_RULES, store, config) != []
    assert blocks(Bundle.STANDING_RULES, store, config) == []


def test_an_overlay_store_is_not_wrapped_as_repository_data(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    produced = blocks(Bundle.STANDING_RULES, store, config)
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


def test_a_note_sized_to_the_margins_edge_is_flagged_oversized(tmp_path: Path) -> None:
    # Sized from `hook_output_chars` and `CAP_MARGIN`, never a literal, so this does not rot
    # when `STANDING_LEAD`'s wording changes. If `_cap` ever stopped subtracting the margin,
    # this block would sit safely under the (wider) cap and go undetected -- that is exactly
    # the regression this pins.
    store, config = a_store(tmp_path)
    for path in store.groups["developer"].glob("*.md"):
        path.unlink()
    name = "solo"
    heading = f"### {name}\n\n"
    cap = config.native_caps.hook_output_chars - CAP_MARGIN
    body = "x" * (cap + 1 - len(heading))
    (store.groups["developer"] / f"{name}.md").write_text(
        note(name, startup="1", body=body), encoding="utf-8"
    )
    report = fit(Bundle.STANDING_RULES, store, config)
    assert report.oversized == 1
    assert report.fits is False


def test_fit_reports_overflow_and_an_oversized_part_separately(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    assert fit(Bundle.STANDING_RULES, store, config).fits is True
    (store.groups["developer"] / "huge.md").write_text(
        note("huge", startup="9", body="word " * 30_000), encoding="utf-8"
    )
    report = fit(Bundle.STANDING_RULES, store, config)
    assert report.oversized == 1
    assert report.fits is False


def test_a_volatile_set_sized_exactly_at_the_budget_is_still_injected_in_full(
    tmp_path: Path,
) -> None:
    # `<=`, and loosening it to `<` left all 617 tests green — every fixture sat comfortably on
    # one side of the line. The comparison decides whether a note set is injected whole or
    # replaced by a list of descriptions, so the boundary is the behaviour: "within budget"
    # has to include the set that is exactly the budget, or the budget means one word less
    # than it says. Sized from the configured value rather than from a literal, so it cannot
    # rot when `VOLATILE_LEAD` is reworded.
    store, config = a_store(tmp_path)
    for path in store.groups["project-volatile"].glob("*.md"):
        path.unlink()
    today = date.today().isoformat()
    heading_words = len(f"### solo (as_of {today})".split())
    budget = config.budgets.effective("volatile_notes_words")
    (store.groups["project-volatile"] / "solo.md").write_text(
        note("solo", as_of=today, body="word " * (budget - heading_words)), encoding="utf-8"
    )
    text = "\n".join(blocks(Bundle.VOLATILE_NOTES, store, config))
    assert "outgrown its budget" not in text
    assert text.count("word") == budget - heading_words

    # One word past it, and the same set is a list of descriptions instead.
    (store.groups["project-volatile"] / "solo.md").write_text(
        note("solo", as_of=today, body="word " * (budget - heading_words + 1)), encoding="utf-8"
    )
    assert "outgrown its budget" in "\n".join(blocks(Bundle.VOLATILE_NOTES, store, config))


def test_an_oversized_part_is_withheld_rather_than_delivered_unterminated(
    tmp_path: Path,
) -> None:
    # `split` never breaks a block, so one block larger than the cap becomes one part larger
    # than the cap. `fit` reported it and `render` handed it out anyway, exiting 0 — and
    # nothing on the hook path runs `fit`, so the only reader of that report was `doctor`.
    # Measured at `hook_output_chars = 10000` before the fix: part 2 was 20,288 characters and
    # arrived carrying **one** of its two region markers. The model got an opening delimiter,
    # the lead sentence "It ends at the matching end marker and nowhere else", and no end
    # marker — the exact state `trust.wrap`'s nonce region exists to make unreachable.
    store, config = a_store(tmp_path, mode="in-repo")
    for path in store.groups["developer"].glob("*.md"):
        path.unlink()
    cap = config.native_caps.hook_output_chars - CAP_MARGIN
    (store.groups["developer"] / "huge.md").write_text(
        note("huge", startup="1", body="x" * (cap * 2)), encoding="utf-8"
    )
    record(store, config)
    assert fit(Bundle.STANDING_RULES, store, config).oversized == 1

    text = render(Bundle.STANDING_RULES, store, config, part=2)
    assert text is not None
    assert len(text) <= cap
    assert "was withheld" in text
    # Neither half of a region, and nothing the repository wrote: an unterminated opening
    # marker is the failure, so the notice must not carry a marker of its own either.
    assert DELIMITER not in text
    assert "x" * 100 not in text
    # The parts that do fit are unaffected — this withholds one slot, not the bundle.
    first = render(Bundle.STANDING_RULES, store, config, part=1)
    assert first is not None and STANDING_LEAD in first


def test_a_part_that_fits_is_never_replaced_by_the_notice(tmp_path: Path) -> None:
    # The other side of the same boundary, and the reason it is `>` and not `>=`: a part packed
    # exactly to `_cap` is the largest one that does fit, and `CAP_MARGIN` is what leaves room
    # for it. Withholding that one would empty a bundle the platform can carry whole.
    store, config = a_store(tmp_path)
    for path in store.groups["developer"].glob("*.md"):
        path.unlink()
    heading = "### solo\n\n"
    cap = config.native_caps.hook_output_chars - CAP_MARGIN
    filler = cap - len(STANDING_LEAD) - len("\n\n") - len(heading)
    (store.groups["developer"] / "solo.md").write_text(
        note("solo", startup="1", body="x" * filler), encoding="utf-8"
    )
    text = render(Bundle.STANDING_RULES, store, config, part=1)
    assert text is not None and len(text) == cap
    assert "was withheld" not in text


def test_many_standing_rules_overflow_the_declared_slots(tmp_path: Path) -> None:
    store, config = a_store(tmp_path)
    for index in range(40):
        (store.groups["developer"] / f"r{index:02d}.md").write_text(
            note(f"r{index:02d}", startup=str(index), body="word " * 400), encoding="utf-8"
        )
    report = fit(Bundle.STANDING_RULES, store, config)
    assert report.parts > report.slots
    assert report.overflow > 0


def test_the_declared_slot_counts_are_the_ones_hooks_json_has_to_ship() -> None:
    # `SLOTS[bundle] >= 1` left three of these four free: only `standing-rules == 3` was
    # asserted anywhere, so `preset-rules`, `volatile-notes` and `index` could each be changed
    # without a test noticing, while every one of them is a count of numbered `hooks.json`
    # entries a session actually gets. The mapping is the contract, so the mapping is pinned —
    # a bundle added or dropped fails this too.
    #
    # The other side of that contract, `hooks/hooks.json` itself, belongs to the `hooks-core`
    # lane and does not exist in this tree: cross-checking these counts against the entries
    # that file declares is that lane's test to write, not one this one can fake.
    assert SLOTS == {
        Bundle.PRESET_RULES: 1,
        Bundle.STANDING_RULES: 3,
        Bundle.VOLATILE_NOTES: 3,
        Bundle.INDEX: 3,
    }


def test_the_margin_is_additive_because_the_text_is_emitted_raw(tmp_path: Path) -> None:
    # The name is a claim about how the text is emitted, and `0 < CAP_MARGIN < 100` — a range
    # check on a constant — demonstrated neither half of it. What makes a margin this small
    # sufficient is that `memory session-context` prints the bundle and one newline: a part
    # packed right up to `_cap` still lands inside `hook_output_chars`, with the rest of the
    # margin as headroom. Through `--json` it does not, and that is the point of the name —
    # `cli._emit` wraps the same string in `json.dumps({"summary": ...}, indent=2)`, whose
    # envelope and escaping alone carry a cap-length bundle past the platform cap.
    # **So the `hooks.json` entries must not pass `--json`** — recorded here because this is
    # the file the `hooks-core` lane reads `SLOTS` out of.
    # (`test_a_note_sized_to_the_margins_edge_is_flagged_oversized` pins the subtraction
    # itself; this pins what the remainder of the margin is for.)
    store, config = a_store(tmp_path)
    for path in store.groups["developer"].glob("*.md"):
        path.unlink()
    heading = "### solo\n\n"
    cap = config.native_caps.hook_output_chars - CAP_MARGIN
    filler = cap - len(STANDING_LEAD) - len("\n\n") - len(heading)
    (store.groups["developer"] / "solo.md").write_text(
        note("solo", startup="1", body="x" * filler), encoding="utf-8"
    )
    text = render(Bundle.STANDING_RULES, store, config, part=1)
    assert text is not None and len(text) == cap
    # Raw: the bundle plus one newline, and the margin is what is left over.
    assert len(text) + 1 <= config.native_caps.hook_output_chars
    assert len(text) + 1 < config.native_caps.hook_output_chars  # headroom, not a dead heat
    # Through the JSON envelope the same text no longer fits, margin and all.
    envelope = json.dumps({"summary": text}, indent=2, sort_keys=True)
    assert len(envelope) > config.native_caps.hook_output_chars


# --- an overlay store built the way overlay mode really builds one ----------------------------
#
# `a_store` above hand-builds a `Store` whose `base` sits *outside* the project root. That is
# the one shape in which the index cannot leak, which is why no test here could ever have
# exercised the shape in which it does: in overlay mode `paths.memory` is a real directory of
# links **inside the repository**, every group resolves out into the overlay, and so
# `inside_project` is False — `may_inject` returns True with no trust record and
# `is_repository_data` returns False, while `store.path / MEMORY.md` is a repository file all
# along. This fixture goes through `resolve()` so the shape is the real one.

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

OVERLAY_CONFIG = """
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
mode = "overlay"
groups = ["developer"]
index_extra = []
"""


def git(root: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)


def a_resolved_overlay_store(tmp_path: Path) -> tuple[Store, Config, Path, Path]:
    root = tmp_path / "project"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", "git@example.com:acme/widget.git")
    overlay = tmp_path / "overlay"
    (overlay / "common" / "memory").mkdir(parents=True)
    (overlay / "common" / "memory" / "keep.md").write_text(
        note("keep", startup="1"), encoding="utf-8"
    )
    (overlay / "projects" / "widget").mkdir(parents=True)
    (overlay / "projects" / "widget" / "project.toml").write_text(
        'remote = "git@example.com:acme/widget.git"\n', encoding="utf-8"
    )
    memory = root / "docs" / "memory"
    memory.mkdir(parents=True)
    (memory / "developer").symlink_to(overlay / "common" / "memory", target_is_directory=True)
    (root / CONFIG_FILE).write_text(OVERLAY_CONFIG, encoding="utf-8")
    machine = tmp_path / "overlay-machine.toml"
    machine.write_text(f'[overlay]\nroot = "{overlay}"\n', encoding="utf-8")
    config = load(root, machine=machine)
    store = resolve(root, config, machine=machine)
    assert store is not None
    assert store.path == memory  # the store really is a directory in the repository
    return store, config, machine, overlay


@needs_git
def test_an_index_symlinked_outside_this_projects_share_is_never_injected(tmp_path: Path) -> None:
    # `_index` reads `store.path / MEMORY.md` through `is_file()`, which follows symlinks, and
    # nothing asks where the link goes — while `worktree._index_source` already applies §9.1's
    # per-link target rule to the very same file for the *link* path. This is the path that
    # reaches the model.
    store, config, _machine, overlay = a_resolved_overlay_store(tmp_path)
    other = overlay / "projects" / "other-client" / "memory"
    other.mkdir(parents=True)
    (other / INDEX_NAME).write_text("# another client's index\n", encoding="utf-8")
    (store.path / INDEX_NAME).symlink_to(other / INDEX_NAME)
    assert blocks(Bundle.INDEX, store, config) == []


@needs_git
def test_an_index_symlinked_inside_this_projects_share_is_still_injected(tmp_path: Path) -> None:
    # §6.3 makes a symlinked index a legitimate member of the tree `attach` creates, so the
    # rule is "inside this project's share", never "refuse every symlinked index".
    store, config, _machine, overlay = a_resolved_overlay_store(tmp_path)
    share = overlay / "projects" / "widget" / "memory"
    share.mkdir(parents=True)
    content = "# Memory Index\n\nA line only this test wrote, not a literal the code repeats.\n"
    (share / INDEX_NAME).write_text(content, encoding="utf-8")
    (store.path / INDEX_NAME).symlink_to(share / INDEX_NAME)
    assert blocks(Bundle.INDEX, store, config) == [content.rstrip("\n")]


@needs_git
def test_an_index_committed_to_the_repository_is_gated_and_wrapped(tmp_path: Path) -> None:
    # A real `MEMORY.md` at `store.path` in overlay mode is a file the clone ships: repository
    # content, however far outside the repository every group resolves.
    store, config, _machine, _ = a_resolved_overlay_store(tmp_path)
    content = "# Memory Index\n\nA line only this test wrote, not a literal the code repeats.\n"
    (store.path / INDEX_NAME).write_text(content, encoding="utf-8")
    assert blocks(Bundle.INDEX, store, config) == []
    record(store, config)
    produced = blocks(Bundle.INDEX, store, config)
    assert produced != []
    assert all(block.startswith(DELIMITER) for block in produced)
    assert content in "\n".join(produced)


@needs_git
def test_the_overlay_groups_themselves_are_neither_gated_nor_wrapped(tmp_path: Path) -> None:
    # Widening the gate for the index must not widen it for the notes: the machine owner's
    # overlay notes are not repository content, and wrapping them as data would defeat every
    # standing rule in the mode this project actually ships.
    store, config, _machine, _ = a_resolved_overlay_store(tmp_path)
    produced = blocks(Bundle.STANDING_RULES, store, config)
    assert produced != []
    assert not any(DELIMITER in block for block in produced)


# --- the slots the index declares have to be fillable ----------------------------------------


def _an_index_of(sections: int, per_section: int) -> str:
    body = "\n".join(f"- [t{i} → a{i}](developer/n{i}.md)" for i in range(per_section))
    return "# Memory Index\n\n" + "\n\n".join(
        f"## Section {s}\n\n{body}\n" for s in range(sections)
    )


def test_an_index_over_one_part_fills_the_second_slot(tmp_path: Path) -> None:
    # `_index` returned the whole file as one block and `split` never breaks a block, so slot 2
    # was dead: a 22,816-byte index — inside `memory_index_bytes` (25600) and inside every
    # other configured cap — packed into one part of 23,126 characters that the harness
    # truncated at 10,000, with part 2 `None` and `keelline memory index` exiting 0 saying
    # "index is current".
    store, config = a_store(tmp_path)
    text = _an_index_of(sections=6, per_section=90)
    assert len(text.encode("utf-8")) < config.native_caps.memory_index_bytes
    (store.path / INDEX_NAME).write_text(text, encoding="utf-8")

    cap = config.native_caps.hook_output_chars - CAP_MARGIN
    assert len(text) > cap, "the fixture has to be bigger than one part or it proves nothing"
    found = fit(Bundle.INDEX, store, config)
    assert found.parts > 1
    assert found.fits
    assert render(Bundle.INDEX, store, config, part=2) is not None
    assert all(
        len(render(Bundle.INDEX, store, config, part=n) or "") <= cap
        for n in range(1, found.parts + 1)
    )


def test_every_section_of_a_split_index_still_reaches_some_part(tmp_path: Path) -> None:
    # Packing must not drop anything: the whole point of numbered slots is that the index
    # arrives in full across them rather than truncated in one.
    store, config = a_store(tmp_path)
    text = _an_index_of(sections=6, per_section=90)
    (store.path / INDEX_NAME).write_text(text, encoding="utf-8")
    found = fit(Bundle.INDEX, store, config)
    joined = "\n\n".join(
        render(Bundle.INDEX, store, config, part=n) or "" for n in range(1, found.parts + 1)
    )
    for section in range(6):
        assert f"## Section {section}" in joined
    assert "- [t89 → a89](developer/n89.md)" in joined


def test_the_slots_the_index_declares_can_hold_an_index_at_its_configured_cap(
    tmp_path: Path,
) -> None:
    # The arithmetic `SLOTS[Bundle.INDEX]` is set from: `memory_index_bytes` over one part's
    # capacity, rounded up. Two could never hold a cap-sized index however well it split.
    _store, config = a_store(tmp_path)
    cap = config.native_caps.hook_output_chars - CAP_MARGIN
    needed = -(-config.native_caps.memory_index_bytes // cap)
    assert SLOTS[Bundle.INDEX] >= needed
