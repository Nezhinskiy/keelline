"""`keelline upgrade` and `keelline uninstall` through the real parser: flags, exit codes, and what
prints.

`tests/project/repos.initialised` runs `init` with `[ci] mode = "none"`, so no case here asks the
network for a pin.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import keelline
from keelline.cli import build_parser, discover_registrars, run
from keelline.project.commands import CI_LEFT, CI_PINNED
from keelline.runner import Completed
from keelline.scaffold import Kind, Location, Manifest, Record, digest
from tests.gitfixture import git, needs_git
from tests.project.repos import forge_record, initialised, tree

FORGED = "docs/\x1b[31mforged.md"
# The commands every shared case runs through, and the invocations that print a report.
COMMANDS = ["upgrade", "uninstall"]
REPORTS = [("upgrade", "--dry-run"), ("uninstall", "--dry-run"), ("uninstall",)]
UNMATCHED = "note: 1 --force path(s) named no file this run had to judge"


def _run(root: Path, tmp_path: Path, *argv: str) -> tuple[int, dict[str, Any]]:
    """The command's `--json` object. A refusal goes to stderr in text mode (`cli._report`), so
    a test that read stdout alone would pass on an empty string."""
    parser = build_parser(discover_registrars())
    flags = ["--root", str(root), "--machine", str(tmp_path / "absent.toml"), "--json"]
    with redirect_stdout(io.StringIO()) as out:
        code = run([*argv, *flags], parser=parser)
    data: dict[str, Any] = json.loads(out.getvalue())
    return code, data


@dataclass
class _Listing:
    """A `Runner` that answers `ls-remote` from a string and reaches no network."""

    stdout: str

    def run(self, argv: list[str], cwd: Path) -> Completed:
        return Completed(0, self.stdout, "")


@needs_git
@pytest.mark.parametrize("command", COMMANDS)
def test_an_uninitialised_repository_exits_two_and_names_what_to_run(
    tmp_path: Path, command: str
) -> None:
    root = tmp_path / "bare"
    root.mkdir()
    code, data = _run(root, tmp_path, command)
    assert code == 2 and "manifest.json is not there" in data["summary"]


@needs_git
def test_a_current_footprint_says_so_and_exits_zero(tmp_path: Path) -> None:
    root = initialised(tmp_path)
    code, data = _run(root, tmp_path, "upgrade", "--dry-run")
    assert code == 0, data["summary"]
    assert data["summary"].splitlines()[0] == "would upgrade:"
    assert "0 to create, 0 to update, 0 to remove" in data["summary"]
    assert {
        "dry_run",
        "moved",
        "held",
        "footprint",
        "writes",
        "skipped",
        "orphans",
        "pin",
        "asked",
    } <= set(data)


@needs_git
@pytest.mark.parametrize("argv", REPORTS)
def test_a_recorded_target_outside_the_path_grammar_prints_as_its_artifact_id(
    tmp_path: Path, argv: tuple[str, ...]
) -> None:
    # `_relocation` answers a forged target with `skip_modified` at that target, and the run goes
    # on: exit 0, the file at the forged path untouched, and nothing of the target printed.
    root = initialised(tmp_path)
    # A committed manifest can carry any `target`. The engine reports a left-behind file at
    # the recorded target, and a report prints targets; only one the path grammar accepts
    # may print.
    forge_record(root, "roadmap", target=FORGED)
    code, data = _run(root, tmp_path, *argv)
    printed = json.dumps(data)
    assert code == 0, data["summary"]
    assert "\\u001b" not in printed and "forged" not in printed
    assert "<roadmap>" in data["summary"]


@needs_git
@pytest.mark.parametrize("command", COMMANDS)
def test_a_force_path_outside_the_root_is_refused_by_rule(tmp_path: Path, command: str) -> None:
    root = initialised(tmp_path)
    code, data = _run(root, tmp_path, command, "--dry-run", "--force", "../elsewhere.md")
    assert code == 2
    assert "elsewhere" not in data["summary"]


@needs_git
def test_a_force_path_that_names_nothing_is_counted(tmp_path: Path) -> None:
    # The roadmap is edited first, so the exact path names an action the run judges and the
    # case-shifted one does not. On an untouched footprint every forced path would be counted,
    # whether or not the comparison worked. Mutation (advisory): count every forced path ->
    # the exact path gains a note and the first assertion reddens.
    root = initialised(tmp_path)
    roadmap = root / "docs" / "roadmap.md"
    roadmap.write_text(roadmap.read_text(encoding="utf-8") + "\nours\n", encoding="utf-8")
    code, data = _run(root, tmp_path, "upgrade", "--dry-run", "--force", "docs/roadmap.md")
    assert code == 0 and UNMATCHED not in data["summary"]
    code, data = _run(root, tmp_path, "upgrade", "--dry-run", "--force", "docs/Roadmap.md")
    assert code == 0
    assert UNMATCHED in data["summary"]


@needs_git
@pytest.mark.parametrize("newer", [False, True], ids=["current", "newer"])
def test_the_ci_line_never_says_a_workflow_it_left_pins_the_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, newer: bool
) -> None:
    """A hand-edited workflow is `skip_modified` and may pin anything, so the CI line must not say
    it pins `[ci] ref`. It did whenever no skip reason was recorded, on a current project and on
    one whose version and ref were held back for exactly that workflow. `--force` with its path
    rewrites it, and then the line may say so.

    Mutation (advisory): key the line on the skip reason alone again -> both cases print
    `CI_PINNED` and the first assertion reddens.
    """
    from keelline import runner as runner_module

    sha = "a" * 40
    listing = f"{sha}\trefs/tags/v{keelline.__version__}\n"
    monkeypatch.setattr(runner_module, "subprocess_runner", lambda: _Listing(listing))
    root = tmp_path / "widget"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", "git@github.com:owner/widget.git")
    code, data = _run(root, tmp_path, "init", "--yes")
    assert code == 0, data["summary"]
    workflow = root / ".github" / "workflows" / "keelline.yml"
    workflow.write_text(workflow.read_text(encoding="utf-8") + "# ours\n", encoding="utf-8")
    if newer:
        monkeypatch.setattr(keelline, "__version__", "9.9.9")
        listing = f"{'c' * 40}\trefs/tags/v9.9.9\n"
    code, data = _run(root, tmp_path, "upgrade")
    assert code == 0, data["summary"]
    lines = data["summary"].splitlines()
    assert CI_LEFT in lines and CI_PINNED not in lines
    assert bool(data["held"]) is newer
    code, data = _run(root, tmp_path, "upgrade", "--force", ".github/workflows/keelline.yml")
    assert code == 0, data["summary"]
    assert CI_PINNED in data["summary"].splitlines()


@needs_git
@pytest.mark.parametrize("command", COMMANDS)
def test_a_region_record_this_build_does_not_produce_is_an_orphan_and_its_host_file_stays(
    tmp_path: Path, command: str
) -> None:
    # A retired record is judged against a whole-file stub, which names no region, so a record
    # saying its artifact lived inside a host file (a region, or keyed entries) is never retired
    # that way: forced, the stub would delete the host file and everything a person wrote in it.
    # It is counted as an orphan, by the one rule both commands apply. The kind is read off the
    # committed manifest, and it can only turn a removal into an orphan. Mutation (oracle): "a
    # region record this build does not produce is retired as a whole file" -> the forced run
    # removes the host file, and the first assertion reddens for both commands.
    root = initialised(tmp_path)
    target = "docs/keelline/rules/python.md"
    host = root / target
    host.parent.mkdir(parents=True, exist_ok=True)
    host.write_text("Our own rules.\n", encoding="utf-8")
    # The digest a region record carries is its body's, never the host file's.
    record = Record(
        id="profile-rules",
        kind=Kind.MANAGED_REGION,
        location=Location.REPO,
        target=target,
        template="profile/python/rules.md",
        version=keelline.__version__,
        sha256=digest("a region body"),
    )
    Manifest.read(root).with_record(record).write(root)
    code, data = _run(root, tmp_path, command, "--force", target)
    assert host.is_file() and host.read_text(encoding="utf-8") == "Our own rules.\n"
    assert code == 0 and data["orphans"] == 1, data["summary"]


@needs_git
def test_uninstall_lists_what_it_leaves_and_exits_zero(tmp_path: Path) -> None:
    root = initialised(tmp_path)
    (root / "docs" / "roadmap.md").write_text("ours\n", encoding="utf-8")
    code, data = _run(root, tmp_path, "uninstall")
    assert code == 0, data["summary"]
    assert data["left"] == ["docs/roadmap.md"]
    assert {"dry_run", "footprint", "once", "left", "orphans", "note", "kept_locally"} <= set(data)
    assert data["summary"].splitlines()[0] == "uninstalled:"


@needs_git
@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
def test_a_file_a_later_pass_deletes_is_never_reported_left_in_place(
    tmp_path: Path, dry_run: bool
) -> None:
    # Keelline's region taken out of `AGENTS.md` by hand: the footprint pass lists the file
    # `skip_modified`, and the write-once pass then removes the untouched skeleton. The file was
    # counted as "left in place, yours now" after it was deleted. Mutation (advisory): drop the
    # `not in gone` filter -> `left` names `AGENTS.md` and the first assertion reddens.
    root = initialised(tmp_path)
    agents = root / "AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    begin, end = "<!-- keelline:harness:begin -->", "<!-- keelline:harness:end -->\n"
    agents.write_text(text[: text.index(begin)] + text[text.index(end) + len(end) :])
    code, data = _run(root, tmp_path, "uninstall", *(("--dry-run",) if dry_run else ()))
    assert code == 0, data["summary"]
    assert data["left"] == [] and "left in place" not in data["summary"]
    assert "skip_modified  AGENTS.md  (retired and hand-edited)" in data["footprint"]
    assert agents.exists() is dry_run


# One removal from each pass: the footprint's body, the write-once pass, the ignore pass, and
# `keelline.toml` itself, which goes last of all.
FAILING = ["docs/roadmap.md", "CLAUDE.md", ".gitignore", "keelline.toml"]


@needs_git
@pytest.mark.parametrize("failing", FAILING)
def test_a_removal_that_fails_part_way_exits_2_keeps_what_was_done_and_a_rerun_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    """Exit 2 is not "nothing was written", and it is never a dead end. Wherever a removal fails,
    what ran stays applied and recorded, `keelline.toml` and the manifest are still there, and
    the next run finishes to the state an uninterrupted run leaves. The failure is the one the
    engine translates: an `OSError` from the removal, which `_remove` turns into a refusal.

    Mutation (declared): `keelline.toml` removed in the write-once pass again -> a failure on
    `CLAUDE.md` or `.gitignore` leaves no configuration, the next run keeps what the manifest
    still records and drops the manifest, and the last assertion reddens.
    """
    import keelline.scaffold.engine as engine
    from keelline import fsops

    root = initialised(tmp_path)
    real = fsops.remove_within

    def fails(where: Path, target: str) -> None:
        if target == failing:
            raise PermissionError(13, "Permission denied")
        real(where, target)

    monkeypatch.setattr(engine, "remove_within", fails)
    code, data = _run(root, tmp_path, "uninstall")
    assert code == 2, data
    assert (root / failing).is_file()
    # Read now and asserted last, so the converged end state is what a wrong order reddens.
    resumable = (root / "keelline.toml").is_file() and (
        root / ".keelline" / "manifest.json"
    ).is_file()
    monkeypatch.setattr(engine, "remove_within", real)
    code, data = _run(root, tmp_path, "uninstall")
    assert code == 0, data
    # Every directory the first run emptied goes too: each pass prunes above what it removed in a
    # `finally`, so the pass that stopped still emptied the directories of the files it took.
    # Mutation (oracle): "a pass that stops part-way leaves the directories it emptied" -> the
    # `docs/roadmap.md` case keeps `docs/`.
    assert tree(root) == {"README.md"}, sorted(tree(root))
    assert resumable
