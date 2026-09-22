from __future__ import annotations

import json
from pathlib import Path

from keelline.overlay.api import requires_of, satisfies
from keelline.overlay.layout import PLUGIN_MANIFEST
from keelline.overlay.template import template_root


def overlay_with(root: Path, requires: object) -> Path:
    """An overlay directory whose manifest declares `requires`; shared with Task 5 and Task 6."""
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    body: dict[str, object] = {"name": "keelline-overlay", "version": "0.0.0"}
    if requires is not None:
        body["keelline"] = {"requires": requires}
    (root / PLUGIN_MANIFEST).write_text(json.dumps(body), encoding="utf-8")
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "keelline-overlay-marketplace", "plugins": []}), encoding="utf-8"
    )
    return root


def test_the_shipped_template_declares_a_floor_this_reader_reads() -> None:
    spec = requires_of(template_root())
    assert spec is not None and satisfies(spec, "0.1.0") is not None


def test_an_absent_declaration_and_an_absent_manifest_both_answer_none(tmp_path: Path) -> None:
    assert requires_of(overlay_with(tmp_path / "a", None)) is None
    assert requires_of(tmp_path / "nowhere") is None
    assert requires_of(overlay_with(tmp_path / "b", " >=0.1.0 ")) == ">=0.1.0"


def test_the_floor_is_compared_as_numbers_not_as_text() -> None:
    # Mutation (comment): compare `running.groups() >= floor.groups()` as strings -> the first
    # line reddens on `>=9.0.0` against `10.0.0`.
    assert satisfies(">=9.0.0", "10.0.0") is True
    assert satisfies(">=0.1.0", "0.1.0") is True
    assert satisfies(">=0.1.0", "0.0.9") is False


def test_any_other_form_is_unreadable_never_satisfied() -> None:
    for spec in ("~=1.0", ">1.0.0", "==0.1.0", ">=1.0", ">=a.b.c", ""):
        assert satisfies(spec, "0.1.0") is None, spec
    assert satisfies(">=0.1.0", "next") is None


def test_a_component_too_long_to_convert_is_unreadable_and_not_an_exception() -> None:
    """`satisfies` answers for every string, which is what its `None` is worth.

    CPython 3.11 refuses `int()` on a string past 4300 digits, so an unbounded `(\\d+)` in
    either pattern turned an overlay manifest an owner can mistype into a `ValueError`: red in
    `doctor` as "this check could not run", and in the session handler swallowed by the
    backstop that then dropped `NOT_ATTACHED` and every other line of the same result. The
    value is asserted rather than the crash, because the crash is the thing being removed.

    Mutation: `mutations.toml`'s "the version grammar stops bounding its components".
    """
    long = "9" * 5000
    assert satisfies(f">={long}.0.0", "0.1.0") is None
    assert satisfies(">=1.0.0", f"{long}.0.0") is None
    # Ten digits, which is the first length past the bound rather than the first past `int()`.
    assert satisfies(">=1234567890.0.0", "0.1.0") is None


def test_only_ascii_digits_are_a_version(tmp_path: Path) -> None:
    """`\\d` matches every Unicode decimal digit and `int()` converts them, so a floor written
    in Eastern Arabic-Indic numerals validated, compared as `>=1.0.0`, and printed back
    verbatim — `requires_of` returns the manifest's own bytes, and the session line and the
    `doctor` row print the spec they validated. A version is ASCII or it is unreadable.

    The digits are spelled as escapes so this file stays ASCII; the manifest a repository
    writes carries them as bytes, which is what the last assertion says."""
    eastern = ">=\u0661.\u0660.\u0660"
    assert satisfies(eastern, "0.1.0") is None
    assert satisfies(">=0.1.0", "\u0661.\u0660.\u0660") is None
    # Non-vacuous: the manifest really does hand this string back, which is why the verdict
    # above is what keeps it out of a line a model reads.
    assert requires_of(overlay_with(tmp_path / "eastern", eastern)) == eastern
