from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path

import pytest

from keelline.config.loader import CONFIG_FILE, load
from keelline.config.paths import PathEscape, contained, validate_paths
from keelline.config.schema import Config, Paths

PATH_NAMES = tuple(f.name for f in fields(Paths))


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
    with pytest.raises(PathEscape, match=r"'\.\.'"):
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
    os.symlink(outside, tmp_path / "docs" / "notes", target_is_directory=True)
    with pytest.raises(PathEscape, match="symlink"):
        contained(tmp_path, "docs/notes")
    allowed = contained(tmp_path, "docs/notes", allow_final_symlink=True)
    assert allowed == tmp_path / "docs" / "notes"


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
        contained(tmp_path, "docs/notes", allow_final_symlink=True)


def test_a_supplied_resolved_root_is_the_one_compared(tmp_path: Path) -> None:
    # `validate_paths` resolves the root once and passes it down. Nothing else reaches the
    # containment comparison — the guards above it refuse every escape a path string can
    # express — so the parameter that feeds it is pinned here rather than through a config.
    (tmp_path / "docs").mkdir()
    assert contained(tmp_path, "docs", resolved_root=tmp_path.resolve()) == tmp_path / "docs"
    with pytest.raises(PathEscape, match="resolves outside the project root"):
        contained(tmp_path, "docs", resolved_root=tmp_path / "elsewhere")


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


def _sample_config(tmp_path: Path) -> Config:
    (tmp_path / CONFIG_FILE).write_text(
        '[keelline]\nversion = "0.1.0"\npreset = "recommended"\n\n[project]\nname = "sample"\n',
        encoding="utf-8",
    )
    return load(tmp_path, machine=tmp_path / "no-machine.toml")


_NOT_EXEMPT = {
    "agents_md",
    "architecture",
    "runbooks",
    "adr",
    "specs",
    "plans",
    "bugs",
    "bug_index",
    "roadmap",
    "roadmap_history",
}


def test_every_configured_path_is_parametrised_here() -> None:
    # The exemption below is checked per field, so a twelfth path added to `Paths` without a
    # row here would inherit whatever `validate_paths` decides for it, untested.
    assert set(PATH_NAMES) == _NOT_EXEMPT | {"memory"}


@pytest.mark.parametrize("name", PATH_NAMES)
def test_the_final_symlink_exemption_holds_for_memory_and_for_no_other_path(
    tmp_path: Path, name: str
) -> None:
    # One negative example cannot tell "only memory" from "anything but that one example":
    # widening the exemption to the other ten paths must fail here, on each of them.
    config = _sample_config(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()

    root = tmp_path / f"root-{name}"
    relative = Path(config.paths.as_dict()[name])
    (root / relative).parent.mkdir(parents=True, exist_ok=True)
    os.symlink(outside, root / relative, target_is_directory=True)

    if name == "memory":
        assert validate_paths(config, root)[name] == root / relative
        return
    with pytest.raises(PathEscape, match="symlink"):
        validate_paths(config, root)
