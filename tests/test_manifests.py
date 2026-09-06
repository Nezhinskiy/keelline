from __future__ import annotations

import json
from pathlib import Path

from keelline import __version__
from keelline.release.versions import check

ROOT = Path(__file__).resolve().parents[1]


def test_claude_manifest_names_the_plugin_its_version_and_titled_user_config() -> None:
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "keelline"
    assert manifest["version"] == __version__
    for key, entry in manifest["userConfig"].items():
        assert entry["title"], key
        assert entry["description"], key


def test_marketplace_has_a_description_and_an_unversioned_entry() -> None:
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert marketplace["name"] == "keelline-marketplace"
    assert marketplace["description"]
    (entry,) = marketplace["plugins"]
    assert entry["name"] == "keelline"
    assert entry["source"] == "./"
    assert "version" not in entry


def test_codex_manifest_carries_no_hooks_or_skills_key() -> None:
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "keelline"
    assert "hooks" not in manifest
    # `claude plugin validate` refuses "../skills/" as a path traversal attempt and
    # reports "./skills/" as not found, because the value resolves relative to
    # .codex-plugin/ itself: no string reaches the root-level skills/ directory from
    # there. Foundation ships no skills, so it omits the key rather than asserting an
    # unreachable path; the Codex skills-path convention is left to the skills lanes,
    # once Codex's own manifest reading has actually been measured.
    assert "skills" not in manifest


def test_the_repository_itself_passes_release_check() -> None:
    assert check(ROOT) == []


def test_no_top_level_bin_directory() -> None:
    assert not (ROOT / "bin").exists()
