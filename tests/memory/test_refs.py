"""Backticked repository paths in notes that no longer resolve, and links across audiences."""

from __future__ import annotations

from pathlib import Path

import pytest

from keelline.config.loader import load
from keelline.config.schema import Config
from keelline.memory.api import resolve, walk
from keelline.memory.refs import audience_violations, check_refs, source_roots, unresolved

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

[paths]
memory = "notes"

[memory]
mode = "in-repo"
groups = ["developer", "project-stable", "project-volatile"]
"""


def project(tmp_path: Path) -> tuple[Path, Config]:
    root = tmp_path / "widget"
    for name in (
        "src/widget",
        "tests",
        "docs",
        "notes/developer",
        "notes/project-stable",
        "notes/project-volatile",
    ):
        (root / name).mkdir(parents=True)
    (root / "keelline.toml").write_text(CONFIG, encoding="utf-8")
    (root / "src" / "widget" / "boot.py").write_text("", encoding="utf-8")
    return root, load(root, machine=tmp_path / "m.toml")


def note(root: Path, group: str, name: str, body: str) -> Path:
    path = root / "notes" / group / f"{name}.md"
    path.write_text(
        f"---\nname: {name}\ndescription: d\nmetadata:\n  type: feedback\n---\n\n{body}",
        encoding="utf-8",
    )
    return path


def findings(root: Path, config: Config) -> list[tuple[str, int | None, str, str]]:
    store = resolve(root, config, machine=root.parent / "m.toml")
    assert store is not None
    walked = walk(store.path, config.memory.groups)
    return [(f.path, f.line, f.detail, f.rule) for f in unresolved(root, config, store, walked)]


def test_a_reference_to_a_deleted_file_is_reported_and_a_live_one_is_not(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    note(root, "developer", "a", "see `src/widget/boot.py`\n\nand `src/gone.py`\n")
    assert findings(root, config) == [("developer/a.md", 10, "src/gone.py", "dead-reference")]


def test_shorthand_under_a_source_root_resolves(tmp_path: Path) -> None:
    # Roots are `ledger.code_roots` plus the parent of every configured document path, never a
    # list of one project's directories. Mutation: make `source_roots` return `("",)` — this
    # reddens.
    root, config = project(tmp_path)
    assert source_roots(root, config) == ("", "src", "tests", "docs")
    note(
        root,
        "developer",
        "a",
        "see `widget/boot.py` (under src) and `boot.py` (a bare filename, prose)\n",
    )
    assert findings(root, config) == []


def test_placeholders_absolute_paths_outside_the_repository_and_fenced_text_are_not_reported(
    tmp_path: Path,
) -> None:
    root, config = project(tmp_path)
    note(
        root,
        "developer",
        "a",
        "`scripts/foo.py` `/etc/nginx/x.conf` `/opt/app/run.sh`\n\n```\n`src/gone.py`\n```\n",
    )
    assert findings(root, config) == []


def test_a_reference_into_the_store_is_settled_against_the_filesystem_not_the_ignore_rules(
    tmp_path: Path,
) -> None:
    # `.gitignore` covers the whole store, so asking it about a note→note reference discards
    # precisely the class this guard exists to find. Mutation: drop the inside-store exemption —
    # this reddens.
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    root, config = project(tmp_path)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    (root / ".gitignore").write_text("notes/\n", encoding="utf-8")
    note(root, "developer", "a", "see `notes/developer/gone.md`\n")
    assert findings(root, config) == [
        ("developer/a.md", 8, "notes/developer/gone.md", "dead-reference")
    ]


def test_a_path_the_repository_ignores_outside_the_store_is_not_reported(tmp_path: Path) -> None:
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    root, config = project(tmp_path)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    (root / ".gitignore").write_text("build/\n", encoding="utf-8")
    note(root, "developer", "a", "see `build/out.py`\n")
    assert findings(root, config) == []


def test_a_group_the_resolver_could_not_provide_is_named_not_silently_skipped(
    tmp_path: Path,
) -> None:
    # A walk that read a subset and reported "nothing stale" is worse than no guard. The
    # record is the resolver's own (`store.unavailable`), reason included.
    root, config = project(tmp_path)
    (root / "notes" / "project-volatile").rmdir()
    store = resolve(root, config, machine=root.parent / "m.toml")
    assert store is not None
    report = check_refs(root, config, store)
    assert list(report.unavailable) == ["project-volatile"]
    assert "not in the store" in report.unavailable["project-volatile"]


def test_a_note_that_will_not_parse_is_reported_not_dropped(tmp_path: Path) -> None:
    # `renumber` reports every file its sweep could not read; a note the walk quarantined is
    # the same claim about the store. Mutation: return `[]` for `unreadable` — this reddens.
    root, config = project(tmp_path)
    (root / "notes" / "developer" / "broken.md").write_text(
        "---\nname: broken\n  nested: yes\n---\n", encoding="utf-8"
    )
    store = resolve(root, config, machine=root.parent / "m.toml")
    assert store is not None
    report = check_refs(root, config, store)
    assert [path.name for path, _ in report.unreadable] == ["broken.md"]
    assert report.findings == []


def test_audience_violations_are_empty_for_a_store_with_no_cross_project_group(
    tmp_path: Path,
) -> None:
    # The rule is §11's: a note in the cross-project group must not link into a project-scoped
    # one. Only an overlay store has such a group, and the overlay fixture is the `attach`
    # lane's — the arm measured here is the one every in-repo store takes.
    root, config = project(tmp_path)
    note(root, "developer", "a", "see [[b]]\n")
    store = resolve(root, config, machine=root.parent / "m.toml")
    assert store is not None
    assert audience_violations(store, config, walk(store.path, config.memory.groups)) == []
