from __future__ import annotations

import pytest

from keelline.scaffold.regions import RegionError, Style, drop, extract, markers, upsert

BEFORE = "# Title\n\nHand-written prose the tool must never touch.\n"


def test_markers_are_the_shapes_the_design_fixes() -> None:
    assert markers("harness", Style.MARKDOWN) == (
        "<!-- keelline:harness:begin -->",
        "<!-- keelline:harness:end -->",
    )
    assert markers("harness", Style.HASH) == (
        "# keelline:harness:begin",
        "# keelline:harness:end",
    )


def test_a_new_region_is_appended_and_the_rest_is_untouched() -> None:
    out = upsert(BEFORE, "harness", "one\ntwo", Style.MARKDOWN)
    assert out.startswith(BEFORE)
    assert extract(out, "harness", Style.MARKDOWN) == "one\ntwo"


def test_an_existing_region_is_replaced_in_place() -> None:
    once = upsert(BEFORE, "harness", "one", Style.MARKDOWN)
    twice = upsert(once + "trailing prose\n", "harness", "two", Style.MARKDOWN)
    assert extract(twice, "harness", Style.MARKDOWN) == "two"
    assert twice.startswith(BEFORE)
    assert twice.endswith("trailing prose\n")


def test_upsert_is_idempotent() -> None:
    once = upsert(BEFORE, "harness", "one", Style.MARKDOWN)
    assert upsert(once, "harness", "one", Style.MARKDOWN) == once


def test_a_body_that_ends_with_a_newline_round_trips_to_itself() -> None:
    # The stamp the engine records is the rendered body; `extract` must agree with it for a
    # template whose content ends in a newline, which every real template does.
    out = upsert(BEFORE, "harness", "one\ntwo\n", Style.MARKDOWN)
    assert extract(out, "harness", Style.MARKDOWN) == "one\ntwo"
    assert upsert(out, "harness", "one\ntwo\n", Style.MARKDOWN) == out


def test_crlf_endings_outside_the_region_survive() -> None:
    text = "# Title\r\n\r\nProse.\r\n"
    out = upsert(text, "harness", "one", Style.MARKDOWN)
    assert out.startswith("# Title\r\n\r\nProse.\r\n")
    assert extract(out, "harness", Style.MARKDOWN) == "one"


def test_an_exotic_line_separator_is_not_normalised() -> None:
    # `str.splitlines()` splits on eleven characters; a rewrite built on it silently turns a
    # form feed inside somebody's prose into a line break.
    text = "para one\x0cpara two\n"
    out = upsert(text, "harness", "one", Style.HASH)
    assert out.startswith("para one\x0cpara two\n")


def test_two_names_coexist() -> None:
    out = upsert(upsert(BEFORE, "a", "A", Style.HASH), "b", "B", Style.HASH)
    assert extract(out, "a", Style.HASH) == "A"
    assert extract(out, "b", Style.HASH) == "B"


def test_an_absent_region_extracts_as_none() -> None:
    assert extract(BEFORE, "harness", Style.MARKDOWN) is None


def test_an_indented_marker_is_still_found() -> None:
    text = BEFORE + "  <!-- keelline:harness:begin -->\nbody\n  <!-- keelline:harness:end -->\n"
    assert extract(text, "harness", Style.MARKDOWN) == "body"


def test_drop_removes_the_region_and_its_markers() -> None:
    out = drop(upsert(BEFORE, "harness", "one", Style.MARKDOWN), "harness", Style.MARKDOWN)
    assert "keelline" not in out
    assert out == BEFORE


def test_dropping_an_absent_region_changes_nothing() -> None:
    assert drop(BEFORE, "harness", Style.MARKDOWN) == BEFORE


def test_an_unterminated_region_refuses() -> None:
    broken = BEFORE + "<!-- keelline:harness:begin -->\nbody\n"
    with pytest.raises(RegionError, match="end"):
        extract(broken, "harness", Style.MARKDOWN)


def test_two_regions_of_one_name_refuse() -> None:
    doubled = upsert(BEFORE, "harness", "one", Style.MARKDOWN)
    doubled += "<!-- keelline:harness:begin -->\nsecond\n<!-- keelline:harness:end -->\n"
    with pytest.raises(RegionError, match="twice"):
        extract(doubled, "harness", Style.MARKDOWN)


def test_a_doubled_begin_marker_with_one_end_refuses() -> None:
    text = (
        BEFORE + "<!-- keelline:harness:begin -->\nfirst\n"
        "<!-- keelline:harness:begin -->\nsecond\n<!-- keelline:harness:end -->\n"
    )
    with pytest.raises(RegionError, match="twice"):
        extract(text, "harness", Style.MARKDOWN)


def test_a_marker_for_another_name_is_not_a_terminator() -> None:
    text = (
        BEFORE + "<!-- keelline:a:begin -->\nA\n<!-- keelline:b:end -->\n<!-- keelline:a:end -->\n"
    )
    assert extract(text, "a", Style.MARKDOWN) == "A\n<!-- keelline:b:end -->"
