"""`config.layout`: every location derived from `[paths]`, spelled in one module."""

from __future__ import annotations

from pathlib import Path

import pytest

from keelline.config.layout import is_adoption_plan, rules_file
from keelline.config.loader import loads
from keelline.config.paths import PathEscape
from keelline.config.schema import Config

DOCUMENT = '[keelline]\nversion = "0.1.0"\n\n[project]\nname = "widget"\n'


def _config(tmp_path: Path, paths: str = "") -> Config:
    text = DOCUMENT + (f"\n[paths]\n{paths}\n" if paths else "")
    return loads(text, tmp_path, machine=tmp_path / "no-machine.toml")


def test_a_profile_s_rules_live_under_the_keelline_directory(tmp_path: Path) -> None:
    assert rules_file(_config(tmp_path), "python") == "docs/keelline/rules/python.md"
    moved = _config(tmp_path, 'keelline = "meta/keelline"')
    assert rules_file(moved, "python") == "meta/keelline/rules/python.md"


def test_the_keelline_directory_is_contained_like_every_other_path(tmp_path: Path) -> None:
    # `validate_paths` walks every `Paths` field, so the new key needs no guard of its own; this
    # proves it reached the walk. `PATH_VALUE` refuses the spelling before `contained()` runs.
    with pytest.raises(PathEscape):
        _config(tmp_path, 'keelline = "../elsewhere"')


@pytest.mark.parametrize(
    ("path", "adoption"),
    [
        ("docs/plans/2026-09-23-keelline-adoption.md", True),
        ("docs/plans/2026-09-23-keelline-adoption-billing.md", True),
        ("docs/plans/2026-09-23-adoption.md", False),
        ("docs/plans/2026-09-23-keellines.md", False),
        ("docs/plans/2026-09-23-keelline-adoption.txt", False),
        ("docs/plans/archive/2026-09-23-keelline-adoption.md", False),
        ("docs/specs/2026-09-23-keelline-adoption-design.md", False),
    ],
    ids=["dated", "with-a-slug", "no-word", "a-longer-word", "not-markdown", "nested", "a-spec"],
)
def test_an_adoption_plan_is_a_plan_whose_name_says_keelline(
    tmp_path: Path, path: str, adoption: bool
) -> None:
    # A plan directly in `[paths] plans`, where `plan check` and the trail look. Mutation: drop
    # the directory comparison and the nested and spec cases redden.
    assert is_adoption_plan(_config(tmp_path), path) is adoption
