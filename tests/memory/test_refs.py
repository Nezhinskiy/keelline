"""Backticked repository paths in notes that no longer resolve, and links across audiences."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run
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


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def flags(root: Path) -> list[str]:
    return ["--root", str(root), "--machine", str(root.parent / "m.toml")]


def test_the_command_says_the_store_resolves_and_names_a_stale_reference_on_one_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # C5: one line per command, and the label carries what this lane computed. The target is
    # repository-authored and belongs in `--json` only.
    root, _config = project(tmp_path)
    note(root, "developer", "a", "see `src/widget/boot.py`\n")
    assert invoke(["memory", "refs", *flags(root)]) == 0
    assert capsys.readouterr().out == "every backticked path in the store resolves\n"
    note(root, "developer", "a", "see `src/gone.py`\n")
    assert invoke(["memory", "refs", "--json", *flags(root)]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["summary"] == "1 stale reference(s): developer/a.md:8 [dead-reference]"
    assert data["findings"][0]["detail"] == "src/gone.py"


def test_a_group_the_resolver_could_not_provide_refuses_rather_than_reporting_a_clean_walk(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Premise 8 keeps the source's "the walk went blind" exit: a walk over a subset that reports
    # nothing stale is worse than no guard, so this is a refusal (2), never findings (1).
    # Mutation: return a `Result` instead of raising — the exit code reddens.
    root, _config = project(tmp_path)
    (root / "notes" / "project-volatile").rmdir()
    assert invoke(["memory", "refs", *flags(root)]) == 2
    assert "project-volatile" in capsys.readouterr().err


def test_a_note_that_will_not_parse_is_counted_on_the_command_line_too(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, _config = project(tmp_path)
    (root / "notes" / "developer" / "broken.md").write_text(
        "---\nname: broken\n  nested: yes\n---\n", encoding="utf-8"
    )
    assert invoke(["memory", "refs", "--json", *flags(root)]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["summary"] == "1 note(s) could not be parsed and were not read"
    assert data["unreadable"] == ["developer/broken.md"]
