from __future__ import annotations

import json
from pathlib import Path

import pytest

from keelline.overlay.api import later, requires_of, satisfies
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


def test_a_manifest_whose_top_level_is_not_an_object_is_nothing_declared(tmp_path: Path) -> None:
    """`json.loads` answers for a list, a string and a number as readily as for an object.

    `raw.get` exists on none of those, so without this arm a manifest an owner can save turned
    `requires_of` into an `AttributeError` out of a function whose docstring promises `None` for
    anything it cannot read — and the two callers rest on that promise: `doctor` renders a raised
    reader as "this check could not run", and the session handler's `except Exception` swallows it
    along with every other line of the same result, `NOT_ATTACHED` included.

    Uncovered before this case, measured with `--cov-report=term-missing` over `tests/doctor
    tests/overlay tests/release`.

    Mutation (oracle): `if not isinstance(raw, dict):` -> `if False:` -> each shape below raises
    instead of answering.
    """
    root = tmp_path / "overlay"
    (root / ".claude-plugin").mkdir(parents=True)
    for body in ("[]", '[{"keelline": {"requires": ">=0.1.0"}}]', '">=0.1.0"', "3", "null"):
        (root / PLUGIN_MANIFEST).write_text(body, encoding="utf-8")
        assert requires_of(root) is None, body


def test_the_floor_is_compared_as_numbers_not_as_text() -> None:
    # Mutation (comment): compare `running.groups() >= floor.groups()` as strings -> the first
    # line reddens on `>=9.0.0` against `10.0.0`.
    #
    # And the boundary itself, which is the classic off-by-one site: a floor a running version
    # meets exactly is met. Mutation: `mutations.toml`'s "the declared floor stops being met by
    # the version that equals it".
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


def test_later_reads_each_version_s_leading_triple_and_answers_none_without_one() -> None:
    # A suffix does not hide a newer release, and a shape with no leading `X.Y.Z` is unknown
    # rather than older: `upgrade` moved `1.0.0-rc1` and `v1.0.0` down to the running `0.1.0`
    # while this answered through `satisfies`, which needs an exact floor.
    assert later("1.0.0-rc1", "0.1.0") is True
    assert later("0.10.0", "0.9.9") is True
    assert later("0.1.0", "0.1.0") is False
    assert later("0.0.9", "0.1.0") is False
    for unreadable in ("v1.0.0", "", "one"):
        assert later(unreadable, "0.1.0") is None, unreadable


@pytest.mark.parametrize(
    ("version", "than", "answer"),
    [
        # A release is later than its own pre-release, whichever side each is on and however the
        # pre-release is spelled; read by the triple alone both of the first two were `False`, and
        # a pre-release build moved a project recording the release down to itself.
        ("1.0.0", "1.0.0rc1", True),
        ("0.2.0", "0.2.0.dev0", True),
        ("1.0.0", "1.0.0-rc.1", True),
        ("1.0.0", "1.0.0a1.dev2", True),
        ("1.0.0rc1", "1.0.0", False),
        ("0.2.0.dev0", "0.2.0", False),
        ("1.0.0rc1", "1.0.0rc1", False),
        # Two pre-releases, or a suffix that is not one, are not ordered: `.post1` is later than
        # the bare version, so reading every suffix as a pre-release would move it backward.
        ("1.0.0rc1", "1.0.0rc2", None),
        ("1.0.0.dev0", "1.0.0rc1", None),
        ("1.0.0.post1", "1.0.0", None),
        ("1.0.0", "1.0.0.post1", None),
        ("1.0.0+local", "1.0.0", None),
        # The triple still decides whenever it differs, whatever follows it.
        ("1.0.1rc1", "1.0.0", True),
        ("0.9.9", "1.0.0rc1", False),
    ],
)
def test_equal_triples_order_a_release_after_its_pre_release_and_nothing_else(
    version: str, than: str, answer: bool | None
) -> None:
    # Mutation (oracle): "a release reads as older than its own pre-release" -> the rows whose
    # answer is `True` with a bare `version` redden.
    assert later(version, than) is answer
