"""`keelline assess` through the real parser: its exit codes, its `--json`, and the one write it
makes, at a constant place a clone can shape only by committing something there."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run
from keelline.config.loader import CONFIG_FILE
from keelline.config.paths import KEELLINE_DIRECTORY
from keelline.project.api import ASSESSMENT
from keelline.project.init import init
from tests.assess.smoke import BASE, smoke_repo
from tests.gitfixture import LsRemote, git, needs_git
from tests.project.repos import repository

CUSTOM_GATE = '\n[gates.custom.tests]\nrun = ["git", "--version"]\n'


def _assess(root: Path, tmp_path: Path, *extra: str) -> int:
    argv = ["assess", "--root", str(root), "--machine", str(tmp_path / "m.toml"), *extra]
    return run(argv, parser=build_parser(discover_registrars()))


@needs_git
def test_assess_exits_zero_and_its_json_is_the_inventory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Mutation: `--json` printing a document whose `items` is emptied (`run_assess` passing
    # `{**document(assessment), "items": []}` to `Result`) -> the equality below reddens, as long
    # as the smoke copy has an item at all, which the first assertion pins.
    root = smoke_repo(tmp_path)
    assert _assess(root, tmp_path, "--base", BASE, "--json") == 0
    printed = json.loads(capsys.readouterr().out)
    written = json.loads((root / ASSESSMENT).read_text(encoding="utf-8"))
    assert written["items"] != []
    assert {k: v for k, v in printed.items() if k != "summary"} == written


@needs_git
def test_assess_exits_one_when_a_gate_would_fail(tmp_path: Path) -> None:
    # Mutation: `exit_code=1 if assessment.would_fail else 0` becomes `exit_code=0` -> reddens.
    root = smoke_repo(tmp_path)
    (root / "AGENTS.md").write_text("".join("word\n" for _ in range(400)), encoding="utf-8")
    assert _assess(root, tmp_path, "--base", BASE) == 1


@needs_git
def test_a_symlinked_keelline_directory_is_a_refusal_and_nothing_is_written_through_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Mutation: drop the `except UnsafePath` in `write` -> the frame reports an internal error,
    # still exit 2, and the message assertion reddens.
    root = smoke_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    keelline_directory = root / KEELLINE_DIRECTORY
    for child in keelline_directory.iterdir():
        child.unlink()
    keelline_directory.rmdir()
    keelline_directory.symlink_to(outside, target_is_directory=True)
    assert _assess(root, tmp_path, "--base", BASE) == 2
    assert f"refusing to write {ASSESSMENT}" in capsys.readouterr().err
    assert list(outside.iterdir()) == []


@needs_git
def test_a_directory_where_the_inventory_goes_is_a_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Mutation: drop the `except IsADirectoryError` in `write` -> an internal error, exit 2, and
    # the message assertion reddens.
    root = smoke_repo(tmp_path)
    held = root / ASSESSMENT / "held.txt"
    held.parent.mkdir()
    held.write_text("a person's file\n", encoding="utf-8")
    assert _assess(root, tmp_path, "--base", BASE) == 2
    assert "something that is not a file is there" in capsys.readouterr().err
    assert held.read_text(encoding="utf-8") == "a person's file\n"


@needs_git
def test_a_link_where_the_inventory_goes_is_replaced_and_its_target_is_untouched(
    tmp_path: Path,
) -> None:
    # No single line reddens this: what holds it is `os.replace` never following a link at its
    # destination, together with `fsops._mode_of` asking `lstat`, so the replacement neither
    # writes through the link nor takes the link's mode.
    root = smoke_repo(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("a file outside the root\n", encoding="utf-8")
    (root / ASSESSMENT).symlink_to(outside)
    assert _assess(root, tmp_path, "--base", BASE) == 0
    assert not (root / ASSESSMENT).is_symlink()
    assert (root / ASSESSMENT).is_file()
    assert outside.read_text(encoding="utf-8") == "a file outside the root\n"


@needs_git
def test_a_custom_gate_runs_beside_the_built_ins(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The fixture is `installed`, so the custom gate enforces from the commit that adds it.
    # Mutation: `config.gates.builtin` passed to `run_gates` in place of `config.gate_names` ->
    # the custom gate never runs and the last gate is `trail`.
    root = smoke_repo(tmp_path)
    with (root / CONFIG_FILE).open("a", encoding="utf-8") as document:
        document.write(CUSTOM_GATE)
    git(root, "commit", "-qam", "chore: a gate of our own")
    assert _assess(root, tmp_path, "--base", "HEAD~1", "--json") == 0
    gates = json.loads(capsys.readouterr().out)["gates"]
    assert gates[-1]["name"] == "tests"
    assert gates[-1]["enforcing"] is True


@needs_git
def test_assess_after_init_with_no_origin_fetched_names_the_gates_that_cannot_judge(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The first thing a person runs after `init`: `origin` is configured and never fetched, so
    # the default base does not exist. `plan` reports it and `commit` could not run; both are
    # failing, so the command exits 1, and the inventory is still written where git ignores it.
    # Mutation (advisory): the default base spelled as `HEAD` -> both gates read an empty
    # range, nothing fails, and the exit code reddens.
    root = repository(tmp_path)
    init(root, machine=tmp_path / "m.toml", runner=LsRemote(), yes=True, dry_run=False, ci=False)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: keelline init")
    assert _assess(root, tmp_path, "--json") == 1
    printed = json.loads(capsys.readouterr().out)
    failing = {g["name"]: g["answered"] for g in printed["gates"] if g["failing"]}
    assert failing == {"plan": True, "commit": False}
    assert printed["base"] == "refs/remotes/origin/main"
    assert git(root, "check-ignore", "--", ASSESSMENT).strip() == ASSESSMENT
