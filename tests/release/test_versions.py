from __future__ import annotations

import json
from pathlib import Path

from keelline.release.versions import check, collect

PYPROJECT = '[project]\nname = "keelline"\nversion = "{v}"\n'
INIT = '__version__ = "{v}"\n'
MARKETPLACE = {"name": "keelline-marketplace", "plugins": [{"name": "keelline", "source": "./"}]}


def repo(
    tmp_path: Path,
    *,
    pyproject: str,
    init: str,
    claude: str,
    codex: str,
    changelog: str,
    fragments: int = 0,
    marketplace: dict[str, object] | None = None,
) -> Path:
    (tmp_path / "src" / "keelline").mkdir(parents=True)
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".codex-plugin").mkdir()
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "pyproject.toml").write_text(PYPROJECT.format(v=pyproject))
    (tmp_path / "src" / "keelline" / "__init__.py").write_text(INIT.format(v=init))
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "keelline", "version": claude})
    )
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(marketplace or MARKETPLACE)
    )
    (tmp_path / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "keelline", "version": codex})
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n<!-- towncrier release notes start -->\n\n"
        f"## {changelog} (2026-09-05)\n"
    )
    for index in range(fragments):
        (tmp_path / "changelog.d" / f"{index}.feature.md").write_text("x\n")
    return tmp_path


def test_all_equal_is_clean(tmp_path: Path) -> None:
    root = repo(
        tmp_path, pyproject="0.1.0", init="0.1.0", claude="0.1.0", codex="0.1.0", changelog="0.1.0"
    )
    assert check(root) == []


def test_each_mismatch_is_named(tmp_path: Path) -> None:
    root = repo(
        tmp_path, pyproject="0.1.0", init="0.1.0", claude="0.1.1", codex="0.1.0", changelog="0.1.0"
    )
    problems = check(root)
    assert len(problems) == 1
    assert ".claude-plugin/plugin.json" in problems[0]
    assert "0.1.1" in problems[0]


def test_pending_fragments_allow_the_changelog_to_lag(tmp_path: Path) -> None:
    root = repo(
        tmp_path,
        pyproject="0.2.0",
        init="0.2.0",
        claude="0.2.0",
        codex="0.2.0",
        changelog="0.1.0",
        fragments=1,
    )
    assert check(root) == []


def test_without_fragments_the_changelog_must_match(tmp_path: Path) -> None:
    root = repo(
        tmp_path, pyproject="0.2.0", init="0.2.0", claude="0.2.0", codex="0.2.0", changelog="0.1.0"
    )
    assert any("CHANGELOG.md" in problem for problem in check(root))


def test_a_versioned_marketplace_entry_is_refused(tmp_path: Path) -> None:
    versioned: dict[str, object] = {
        "name": "m",
        "plugins": [{"name": "keelline", "source": "./", "version": "0.1.0"}],
    }
    root = repo(
        tmp_path,
        pyproject="0.1.0",
        init="0.1.0",
        claude="0.1.0",
        codex="0.1.0",
        changelog="0.1.0",
        marketplace=versioned,
    )
    assert any("marketplace" in problem for problem in check(root))


def test_collect_reads_every_source_value(tmp_path: Path) -> None:
    root = repo(
        tmp_path, pyproject="1.0.0", init="1.0.1", claude="1.0.2", codex="1.0.3", changelog="1.0.4"
    )
    assert collect(root) == {
        "pyproject.toml": "1.0.0",
        "src/keelline/__init__.py": "1.0.1",
        ".claude-plugin/plugin.json": "1.0.2",
        ".codex-plugin/plugin.json": "1.0.3",
        "CHANGELOG.md": "1.0.4",
    }


def test_a_missing_version_key_reads_as_none(tmp_path: Path) -> None:
    root = repo(
        tmp_path, pyproject="1.0.0", init="1.0.0", claude="1.0.0", codex="1.0.0", changelog="1.0.0"
    )
    (root / ".codex-plugin" / "plugin.json").write_text(json.dumps({"name": "keelline"}))
    assert collect(root)[".codex-plugin/plugin.json"] is None
