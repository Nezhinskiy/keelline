from __future__ import annotations

import os
from pathlib import Path

import pytest

from keelline.config.loader import CONFIG_FILE, load
from keelline.config.paths import PathEscape, contained, validate_paths


def test_a_plain_relative_path_resolves_under_the_root(tmp_path: Path) -> None:
    assert contained(tmp_path, "docs/specs") == tmp_path / "docs" / "specs"


@pytest.mark.parametrize(
    "relative",
    [
        "../sibling",
        "docs/../../x",
        "/etc/keelline",
        "",
        ".",
        "./",
        "././",
        "./.",
        "docs/./../..",
    ],
)
def test_escapes_are_refused(tmp_path: Path, relative: str) -> None:
    with pytest.raises(PathEscape):
        contained(tmp_path, relative)


def test_dotdot_is_refused_even_when_it_resolves_inside_the_root(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    with pytest.raises(PathEscape, match="'..'"):
        contained(tmp_path, "docs/../docs/specs")


def test_a_symlinked_intermediate_directory_is_refused(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathEscape, match="symlink"):
        contained(tmp_path, "docs/specs")


def test_a_symlink_pointing_inside_the_root_is_still_refused(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "docs").symlink_to(tmp_path / "real", target_is_directory=True)
    with pytest.raises(PathEscape, match="symlink"):
        contained(tmp_path, "docs/specs")


def test_a_final_symlink_is_refused_unless_allowed(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-store"
    outside.mkdir()
    (tmp_path / "docs").mkdir()
    os.symlink(outside, tmp_path / "docs" / "memory", target_is_directory=True)
    with pytest.raises(PathEscape, match="symlink"):
        contained(tmp_path, "docs/memory")
    allowed = contained(tmp_path, "docs/memory", allow_final_symlink=True)
    assert allowed == tmp_path / "docs" / "memory"


def test_a_symlinked_root_does_not_confuse_containment(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    assert contained(link, "docs") == link / "docs"


def test_allow_final_symlink_does_not_relax_an_intermediate_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "docs").symlink_to(real, target_is_directory=True)
    with pytest.raises(PathEscape, match="symlink"):
        contained(tmp_path, "docs/memory", allow_final_symlink=True)


def test_validate_paths_allows_a_final_symlink_only_for_the_memory_path(tmp_path: Path) -> None:
    (tmp_path / CONFIG_FILE).write_text(
        '[keelline]\nversion = "0.1.0"\npreset = "recommended"\n\n[project]\nname = "sample"\n',
        encoding="utf-8",
    )
    config = load(tmp_path, machine=tmp_path / "no-machine.toml")

    outside = tmp_path / "outside"
    outside.mkdir()

    accepted_root = tmp_path / "accepted"
    (accepted_root / "docs").mkdir(parents=True)
    (accepted_root / "docs" / "memory").symlink_to(outside, target_is_directory=True)
    result = validate_paths(config, accepted_root)
    assert result["memory"] == accepted_root / "docs" / "memory"

    refused_root = tmp_path / "refused"
    (refused_root / "docs").mkdir(parents=True)
    (refused_root / "docs" / "specs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathEscape, match="symlink"):
        validate_paths(config, refused_root)
