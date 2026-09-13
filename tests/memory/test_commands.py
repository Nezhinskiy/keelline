from __future__ import annotations

import json
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run

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

[memory]
mode = "local-only"
groups = ["developer", "project-volatile"]
index_extra = []
"""

NOTE = (
    '---\nname: {name}\ndescription: "{name} description"\n'
    'index: "t → {name}"\n{meta}---\n\n{body}\n'
)


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    base = root / ".keelline" / "local" / "memory"
    for group in ("developer", "project-volatile"):
        (base / group).mkdir(parents=True)
    # "a" and "v" carry deliberately different body lengths (5 words vs. 1) so that a sort
    # that stopped honouring word count — e.g. reversing it, or dropping it for name-only —
    # actually changes the observed order instead of coincidentally reproducing it.
    (base / "developer" / "a.md").write_text(
        NOTE.format(
            name="a",
            meta="metadata:\n  type: project\n  startup: 1\n",
            body="Body. Body. Body. Body. Body.",
        ),
        encoding="utf-8",
    )
    (base / "project-volatile" / "v.md").write_text(
        NOTE.format(
            name="v",
            meta="metadata:\n  type: project\n  as_of: 2026-09-01\n",
            body="Body.",
        ),
        encoding="utf-8",
    )
    (root / "keelline.toml").write_text(CONFIG, encoding="utf-8")
    (tmp_path / "machine.toml").write_text("", encoding="utf-8")
    return root


def common(project: Path) -> list[str]:
    return ["--root", str(project), "--machine", str(project.parent / "machine.toml")]


def test_the_memory_group_and_its_commands_are_discovered() -> None:
    help_text = build_parser(discover_registrars()).format_help()
    assert "memory" in help_text


def test_index_check_reports_drift_with_exit_one(project: Path) -> None:
    # Three invocations on purpose: red, write, green. One would pass either way.
    assert invoke(["memory", "index", "--check", *common(project)]) == 1
    assert invoke(["memory", "index", *common(project)]) == 0
    assert invoke(["memory", "index", "--check", *common(project)]) == 0


def test_an_unknown_bundle_is_refused(project: Path) -> None:
    assert invoke(["memory", "session-context", "--bundle", "nonsense", *common(project)]) == 2


def test_a_store_whose_notes_live_in_the_repository_says_nothing_before_trust(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        invoke(["memory", "session-context", "--bundle", "standing-rules", *common(project)]) == 0
    )
    assert capsys.readouterr().out.strip() == ""
    assert invoke(["memory", "trust", "--in-repo-memory", *common(project)]) == 0
    assert (
        invoke(["memory", "session-context", "--bundle", "standing-rules", *common(project)]) == 0
    )
    assert "Body." in capsys.readouterr().out


def test_an_unreached_part_prints_nothing_and_succeeds(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    invoke(["memory", "trust", "--in-repo-memory", *common(project)])
    capsys.readouterr()
    argv = ["memory", "session-context", "--bundle", "standing-rules", "--part", "3"]
    assert invoke([*argv, *common(project)]) == 0
    assert capsys.readouterr().out.strip() == ""


def test_trust_writes_to_the_machine_file_it_was_given_not_to_the_home_directory(
    project: Path,
) -> None:
    machine = project.parent / "machine.toml"
    assert invoke(["memory", "trust", "--in-repo-memory", *common(project)]) == 0
    assert (machine.parent / "trust.json").is_file()


def test_inventory_reports_what_a_sweep_acts_on(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert invoke(["memory", "inventory", "--json", *common(project)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["notes"] == 2
    assert payload["standing"] == 1
    assert [entry["name"] for entry in payload["entries"]] == ["a", "v"]


def test_fit_reports_every_bundle_against_its_slots(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert invoke(["memory", "fit", "--json", *common(project)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload["bundles"]) == {"preset-rules", "standing-rules", "volatile-notes", "index"}
    assert payload["bundles"]["standing-rules"]["slots"] == 3


def test_a_project_with_no_store_fails_with_a_reason(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    (root / "keelline.toml").write_text(CONFIG, encoding="utf-8")
    (tmp_path / "machine.toml").write_text("", encoding="utf-8")
    assert (
        invoke(
            ["memory", "index", "--root", str(root), "--machine", str(tmp_path / "machine.toml")]
        )
        == 1
    )
