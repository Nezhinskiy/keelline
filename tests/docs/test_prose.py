from __future__ import annotations

from keelline.prose import blank_code_spans, blank_fences, path_references


def test_a_backticked_path_with_a_slash_is_a_reference_and_a_bare_filename_is_prose() -> None:
    assert list(path_references("see `src/widget/boot.py` and `config.py`")) == [
        "src/widget/boot.py"
    ]


def test_a_location_suffix_is_not_part_of_the_name() -> None:
    assert list(path_references("`src/a.py:12` and `tests/test_a.py::test_x`")) == [
        "src/a.py",
        "tests/test_a.py",
    ]


def test_typescript_and_toml_count_as_files_this_grammar_stores() -> None:
    # The drift that built this module: one reader accepted `.ts`/`.tsx` and the other did not.
    # Mutation: drop `tsx?` from `REFERENCE` — this reddens.
    assert list(path_references("`web/app.tsx` `web/x.ts` `cfg/a.toml` `k/v.yaml`")) == [
        "web/app.tsx",
        "web/x.ts",
        "cfg/a.toml",
        "k/v.yaml",
    ]


def test_a_shell_command_or_a_url_is_never_a_reference() -> None:
    assert list(path_references("`python3 scripts/x.py --root .` `https://example.com/a.py`")) == []


def test_fences_are_blanked_not_deleted_so_line_numbers_hold() -> None:
    text = "a\n```\n`x/y.py`\n```\nb\n~~~\n`p/q.py`\n~~~\nc\n"
    blanked = blank_fences(text)
    assert blanked.count("\n") == text.count("\n")
    assert "x/y.py" not in blanked and "p/q.py" not in blanked
    assert blanked.splitlines()[-1] == "c"


def test_code_spans_are_replaced_by_a_placeholder_that_keeps_neighbours_apart() -> None:
    # Removing a span would leave `[[a]] [[a]]` where the text had `[[a]] `x` [[a]]`; the
    # graph check reads that as a repeated link. Mutation: replace with "" — this reddens.
    assert blank_code_spans("[[a]] `x` [[a]]") == "[[a]] \x00 [[a]]"
    assert blank_code_spans("no code") == "no code"
