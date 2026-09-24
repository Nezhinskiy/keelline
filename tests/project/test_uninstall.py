"""`keelline uninstall`: what Keelline wrote goes, what a person wrote stays and is named."""

from __future__ import annotations

import contextlib
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

import keelline
from keelline.attach.api import LEDGER
from keelline.config.loader import CONFIG_FILE
from keelline.errors import Refusal
from keelline.project.uninstall import (
    ATTACHED,
    KEPT_AFTER,
    KEPT_LOCALLY,
    NO_CONFIG,
    NOTHING,
    ORDER_NOTE,
    UninstallReport,
    uninstall,
)
from keelline.project.upgrade import upgrade
from keelline.scaffold import MANIFEST_PATH, Kind, Location, Manifest, Record, Verb, digest
from tests.gitfixture import LsRemote, needs_git, run_git
from tests.project.repos import BEFORE, initialised, tree
from tests.snapshot import assert_snapshot_unchanged, snapshot

LOCAL_ROADMAP = f'''[keelline]
version = "{keelline.__version__}"

[project]
name = "widget"

[artifacts]
local = ["roadmap"]

[ci]
mode = "none"
'''


def _uninstall(
    root: Path, tmp_path: Path, *, dry_run: bool = False, force: tuple[str, ...] = ()
) -> UninstallReport:
    return uninstall(root, machine=tmp_path / "absent.toml", dry_run=dry_run, force=force)


@needs_git
def test_an_untouched_footprint_leaves_only_what_was_there_before(tmp_path: Path) -> None:
    root = initialised(tmp_path)
    report = _uninstall(root, tmp_path)
    assert tree(root) == {"README.md"}
    assert (root / "README.md").read_text(encoding="utf-8") == BEFORE
    # The report is what ran: the skeleton judged after its region left, and removed, where the
    # plan made before the first pass called it edited. Mutation (advisory): return the plans
    # made before any write -> `AGENTS.md` is reported left in place, and this reddens.
    assert [a.verb for a in report.once.actions if a.artifact_id == "agents-skeleton"] == [
        Verb.REMOVE
    ]
    assert not [
        a for a in (*report.footprint.actions, *report.once.actions) if a.verb is Verb.SKIP_MODIFIED
    ]


@needs_git
def test_an_edited_file_stays_and_is_listed_and_force_takes_it(tmp_path: Path) -> None:
    root = initialised(tmp_path)
    roadmap = root / "docs" / "roadmap.md"
    roadmap.write_text(roadmap.read_text(encoding="utf-8") + "\nours\n", encoding="utf-8")
    report = _uninstall(root, tmp_path)
    left = {a.target for a in report.footprint.actions if a.verb is Verb.SKIP_MODIFIED}
    assert left == {"docs/roadmap.md"}
    assert roadmap.is_file() and not (root / MANIFEST_PATH).exists()


@needs_git
def test_force_removes_the_edited_file_it_names(tmp_path: Path) -> None:
    root = initialised(tmp_path)
    roadmap = root / "docs" / "roadmap.md"
    roadmap.write_text("ours\n", encoding="utf-8")
    _uninstall(root, tmp_path, force=("docs/roadmap.md",))
    assert not roadmap.exists()


@needs_git
def test_text_a_person_added_around_the_region_keeps_agents_md(tmp_path: Path) -> None:
    root = initialised(tmp_path)
    agents = root / "AGENTS.md"
    agents.write_text("Our preface.\n" + agents.read_text(encoding="utf-8"), encoding="utf-8")
    _uninstall(root, tmp_path)
    text = agents.read_text(encoding="utf-8")
    assert text.startswith("Our preface.\n") and "keelline:harness" not in text


@needs_git
def test_forcing_agents_md_takes_the_region_out_and_keeps_the_skeleton_s_prose(
    tmp_path: Path,
) -> None:
    # `AGENTS.md` is two artifacts: Keelline's region, and the skeleton a person writes into.
    # Forcing the path is the only way to take an edited region out, and it must not reach the
    # write-once pass, where it would delete the skeleton and every line written into it.
    root = initialised(tmp_path)
    agents = root / "AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    edited = text.replace(
        "<!-- keelline:harness:begin -->\n", "<!-- keelline:harness:begin -->\nOur line.\n"
    )
    agents.write_text("Our preface.\n" + edited, encoding="utf-8")
    _uninstall(root, tmp_path, force=("AGENTS.md",))
    kept = agents.read_text(encoding="utf-8")
    assert kept.startswith("Our preface.\n") and "keelline:harness" not in kept


@needs_git
@pytest.mark.parametrize("forced", [False, True], ids=["plain", "region-forced"])
def test_a_person_s_lines_in_gitignore_stay_when_the_ignore_region_goes(
    tmp_path: Path, forced: bool
) -> None:
    # A region's host file is somebody's: what leaves is the region, never the file around it,
    # and forcing overrides the hand-edit verdict and not the payload. With the region edited
    # the plain run leaves it, markers and all, and the forced run takes the region alone.
    # Mutation (advisory): `_removal_payload` answers `None` for a managed region -> the host
    # file is deleted with the person's lines in it, and the first assertion reddens.
    root = initialised(tmp_path)
    ignore = root / ".gitignore"
    ours = "# ours\nbuild/\n"
    text = ignore.read_text(encoding="utf-8")
    edited = text.replace(".keelline/assessment.json", ".keelline/assessment.json\nextra/")
    ignore.write_text(ours + edited, encoding="utf-8")
    _uninstall(root, tmp_path, force=(".gitignore",) if forced else ())
    kept = ignore.read_text(encoding="utf-8")
    assert kept.startswith(ours)
    assert ("keelline:ignore" in kept) is not forced


@needs_git
def test_a_region_record_this_build_does_not_produce_is_an_orphan_and_its_host_file_stays(
    tmp_path: Path,
) -> None:
    # A retired artifact this build no longer produces is judged against a whole-file stub,
    # which carries no region name. A record saying its artifact lived inside a host file (a
    # region, or keyed entries) is therefore never retired that way: forced, the stub would
    # delete the host file and everything a person wrote in it. It is counted as an orphan. The
    # kind is read off the committed manifest, and it can only turn a removal into an orphan.
    # Mutation (declared): every record is offered for retirement whatever its kind -> the
    # forced run deletes the host file, and the first assertion reddens.
    root = initialised(tmp_path)
    target = "docs/keelline/rules/python.md"
    host = root / target
    host.parent.mkdir(parents=True, exist_ok=True)
    host.write_text("Our own rules.\n", encoding="utf-8")
    # The digest a region record carries is its body's, never the host file's.
    manifest = Manifest.read(root)
    record = Record(
        id="profile-rules",
        kind=Kind.MANAGED_REGION,
        location=Location.REPO,
        target=target,
        template="profile/python/rules.md",
        version=keelline.__version__,
        sha256=digest("a region body"),
    )
    manifest.with_record(record).write(root)
    report = _uninstall(root, tmp_path, force=(target,))
    assert host.is_file() and host.read_text(encoding="utf-8") == "Our own rules.\n"
    assert report.orphans == 1


@needs_git
def test_a_dry_run_writes_nothing_and_says_the_skeleton_is_judged_after_its_region(
    tmp_path: Path,
) -> None:
    # Mutation (oracle, advisory): set the note on the real run too -> the last assertion
    # reddens.
    root = initialised(tmp_path)
    before = snapshot(root)
    report = _uninstall(root, tmp_path, dry_run=True)
    assert_snapshot_unchanged(root, before)
    assert report.note == ORDER_NOTE
    real = _uninstall(root, tmp_path)
    assert real.note == "" and not (root / "AGENTS.md").exists()


@needs_git
def test_an_attached_repository_is_refused_and_told_to_detach(tmp_path: Path) -> None:
    root = initialised(tmp_path)
    (root / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (root / LEDGER).write_text("{}", encoding="utf-8")
    # The ledger lives under `.keelline/local/`, so without this refusal the count of files kept
    # out of git would still stop the real run, with a remedy that is not the one. The dry run
    # tells them apart: it reports that count, and it refuses an attached repository.
    for dry_run in (True, False):
        with pytest.raises(Refusal, match=re.escape(ATTACHED)):
            _uninstall(root, tmp_path, dry_run=dry_run)
    assert (root / MANIFEST_PATH).is_file()


@needs_git
def test_notes_kept_out_of_git_refuse_the_run_that_would_expose_them(tmp_path: Path) -> None:
    # The local-only store is the preset's default, and the ignore region this run removes is
    # all that keeps it out of git. The count is reported by the dry run and refuses the real
    # one before anything is written; neither names a note. The snapshot is compared whatever the
    # refusal says, so a run that starts removing and refuses later fails on the writes.
    root = initialised(tmp_path)
    note = root / ".keelline" / "local" / "memory" / "developer" / "private-note.md"
    note.parent.mkdir(parents=True)
    note.write_text("a private note\n", encoding="utf-8")
    before = snapshot(root)
    assert _uninstall(root, tmp_path, dry_run=True).kept_locally == 1
    with pytest.raises(Refusal) as refused:
        _uninstall(root, tmp_path)
    assert_snapshot_unchanged(root, before)
    assert str(refused.value) == KEPT_LOCALLY.format(count=1)
    assert "private-note" not in str(refused.value)


@needs_git
def test_an_artifact_kept_out_of_git_goes_with_the_rest(tmp_path: Path) -> None:
    root = initialised(tmp_path, document=LOCAL_ROADMAP)
    assert (root / ".keelline" / "local" / "artifacts" / "docs" / "roadmap.md").is_file()
    _uninstall(root, tmp_path)
    assert not (root / ".keelline").exists()


@needs_git
def test_an_edited_artifact_kept_out_of_git_refuses_until_it_is_forced(tmp_path: Path) -> None:
    root = initialised(tmp_path, document=LOCAL_ROADMAP)
    local = root / ".keelline" / "local" / "artifacts" / "docs" / "roadmap.md"
    local.write_text("private plans\n", encoding="utf-8")
    dry = _uninstall(root, tmp_path, dry_run=True)
    assert [a.verb for a in dry.footprint.actions if a.artifact_id == "roadmap"] == [
        Verb.SKIP_MODIFIED
    ]
    before = snapshot(root)
    with pytest.raises(Refusal) as refused:
        _uninstall(root, tmp_path)
    assert_snapshot_unchanged(root, before)
    assert str(refused.value) == KEPT_LOCALLY.format(count=1)
    _uninstall(root, tmp_path, force=(".keelline/local/artifacts/docs/roadmap.md",))
    assert not (root / ".keelline").exists()


LOCAL_AGENTS = ".keelline/local/artifacts/AGENTS.md"
AGENTS_PLACEMENTS = {
    "committed": (),
    "region-local": ("agents-md",),
    "skeleton-local": ("agents-skeleton",),
    "both-local": ("agents-md", "agents-skeleton"),
}


def _agents_local(local: tuple[str, ...]) -> str:
    return LOCAL_ROADMAP.replace('local = ["roadmap"]', f"local = {json.dumps(list(local))}")


def _ignored(root: Path, path: Path) -> bool:
    # The sealed environment: a global excludes file cannot make a leaked file read as ignored.
    relative = path.relative_to(root).as_posix()
    return run_git(root, "check-ignore", "-q", "--", relative).returncode == 0


@needs_git
@pytest.mark.parametrize("forced", [False, True], ids=["plain", "region-forced"])
@pytest.mark.parametrize("placement", sorted(AGENTS_PLACEMENTS))
def test_a_person_s_line_in_agents_md_survives_every_placement_and_stays_ignored(
    tmp_path: Path, placement: str, forced: bool
) -> None:
    """`AGENTS.md`'s region and its skeleton can each be kept out of git, so the file a person
    writes in may be the committed one, the local one, or both, and `--force` may name the
    region's file. In every combination the person's line survives, and whatever is left under
    `.keelline/local/` when the run ends, finished or refused, is still ignored by git.

    Mutations (declared): the force filter compares `Template.target` instead of the engine's
    effective path -> `both-local` with `region-forced` deletes the file; the check after the
    write-once pass dropped -> `both-local` takes the ignore block out over the remainder.
    """
    local = AGENTS_PLACEMENTS[placement]
    root = initialised(tmp_path, document=_agents_local(local))
    region = LOCAL_AGENTS if "agents-md" in local else "AGENTS.md"
    written = [path for path in ("AGENTS.md", LOCAL_AGENTS) if (root / path).is_file()]
    for path in written:
        with (root / path).open("a", encoding="utf-8") as stream:
            stream.write("\nA LINE OF OURS\n")
    with contextlib.suppress(Refusal):
        _uninstall(root, tmp_path, force=(region,) if forced else ())
    for path in written:
        assert "A LINE OF OURS" in (root / path).read_text(encoding="utf-8"), path
    kept = root / ".keelline" / "local"
    left = [p for p in kept.rglob("*") if p.is_file()] if kept.is_dir() else []
    assert all(_ignored(root, p) for p in left), left


@needs_git
def test_an_untouched_agents_md_kept_out_of_git_goes_whole(tmp_path: Path) -> None:
    # Region and skeleton share `.keelline/local/artifacts/AGENTS.md`. What the region's removal
    # leaves is exactly the skeleton `init` wrote, so the prediction before any write counts the
    # file as going, and it goes. Mutation (advisory): the prediction never credits a remainder
    # -> the run refuses before any write, and this reddens at the call.
    root = initialised(tmp_path, document=_agents_local(("agents-md", "agents-skeleton")))
    assert (root / LOCAL_AGENTS).is_file()
    _uninstall(root, tmp_path)
    # `keelline.toml` was written by the test before `init` adopted it, so it is the person's.
    assert tree(root) == {"README.md", "keelline.toml"}


@needs_git
@pytest.mark.parametrize("edit", ["skeleton", "region"])
def test_a_shared_agents_md_kept_out_of_git_that_will_stay_refuses_before_any_write(
    tmp_path: Path, edit: str
) -> None:
    """Region and skeleton both kept out of git share one file. With a person's line in the
    skeleton, the file stays whatever is forced: the region's force never reaches the skeleton.
    With the region edited, it stays unforced. Either way the run knows before it writes, and
    refuses with the remedy that works: move it out. A first draft counted every action at that
    path as a deletion, started removing, and refused part-way telling the person to force a
    path that is never forced there, which refused the same way on every run.

    Mutation (declared): every action at that path counted as going, the first draft's rule ->
    the dry run's count comes back 0, and this reddens there; the real run would remove the
    footprint before refusing.
    """
    root = initialised(tmp_path, document=_agents_local(("agents-md", "agents-skeleton")))
    local = root / LOCAL_AGENTS
    text = local.read_text(encoding="utf-8")
    if edit == "skeleton":
        local.write_text(text + "\nA LINE OF OURS\n", encoding="utf-8")
    else:
        local.write_text(
            text.replace(
                "<!-- keelline:harness:begin -->\n", "<!-- keelline:harness:begin -->\nX\n"
            ),
            encoding="utf-8",
        )
    before = snapshot(root)
    assert _uninstall(root, tmp_path, dry_run=True).kept_locally == 1
    for force in ((), (LOCAL_AGENTS,)) if edit == "skeleton" else ((),):
        with pytest.raises(Refusal) as refused:
            _uninstall(root, tmp_path, force=force)
        assert_snapshot_unchanged(root, before)
        assert str(refused.value) == KEPT_LOCALLY.format(count=1)


@needs_git
def test_the_disk_after_the_write_once_pass_keeps_the_ignore_block_when_the_prediction_misses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The count before any write is a prediction; the disk after the write-once pass is the
    fact. Made to miss (it credits the remainder the skeleton pass then keeps), the run must
    still stop before the ignore block goes, with the file ignored and the manifest in place.

    Mutation (declared): the check after the write-once pass dropped -> the ignore block goes
    over the remainder, and the file stops being ignored.
    """
    import keelline.project.uninstall as module

    monkeypatch.setattr(module, "matches_render", lambda template, text: True)
    root = initialised(tmp_path, document=_agents_local(("agents-md", "agents-skeleton")))
    local = root / LOCAL_AGENTS
    local.write_text(local.read_text(encoding="utf-8") + "\nA LINE OF OURS\n", encoding="utf-8")
    with pytest.raises(Refusal, match=re.escape(KEPT_AFTER.format(count=1))):
        _uninstall(root, tmp_path)
    assert "A LINE OF OURS" in local.read_text(encoding="utf-8")
    assert _ignored(root, local)
    assert (root / MANIFEST_PATH).is_file()


@needs_git
def test_a_dry_run_that_refuses_still_counts_what_is_kept_out_of_git(tmp_path: Path) -> None:
    # A plan with a refusal is still a report, and the refusal the real run would meet after the
    # finding is fixed is part of it. Mutation (advisory): report 0 whenever a plan refuses ->
    # the count comes back 0, and this reddens.
    root = initialised(tmp_path)
    agents = root / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace("<!-- keelline:harness:begin -->\n", ""),
        encoding="utf-8",
    )
    note = root / ".keelline" / "local" / "memory" / "developer" / "private-note.md"
    note.parent.mkdir(parents=True)
    note.write_text("a private note\n", encoding="utf-8")
    report = _uninstall(root, tmp_path, dry_run=True)
    assert [r.artifact_id for r in report.footprint.refusals] == ["agents-md"]
    assert report.kept_locally == 1


@needs_git
def test_a_remainder_kept_out_of_git_is_counted_before_anything_is_written(tmp_path: Path) -> None:
    """The region kept out of git, with a line of a person's outside it: taking the region out
    leaves the line, so the file stays, and the ignore block must stay over it. A first draft
    counted every `REMOVE` as a deletion and took the ignore block out.

    Mutation (declared): `unlinks` answers every `REMOVE` -> the run gets past the first check
    and refuses later, with the other message, and this reddens.
    """
    root = initialised(tmp_path, document=_agents_local(("agents-md",)))
    with (root / LOCAL_AGENTS).open("a", encoding="utf-8") as stream:
        stream.write("\nA LINE OF OURS\n")
    before = snapshot(root)
    assert _uninstall(root, tmp_path, dry_run=True).kept_locally == 1
    with pytest.raises(Refusal, match=re.escape(KEPT_LOCALLY.format(count=1))):
        _uninstall(root, tmp_path)
    assert_snapshot_unchanged(root, before)


@needs_git
def test_a_missing_keelline_toml_leaves_the_recorded_files_and_converges(tmp_path: Path) -> None:
    # A run that died after its write-once pass, or a person, removed `keelline.toml` and left the
    # manifest. Nothing can be judged without the configuration, so the files stay, their count is
    # reported, and the ledger goes: `init` no longer refuses the repository, and nor does this.
    # Mutation (advisory): the ledger kept on this path -> the second run finds the manifest and
    # does not refuse with `NOTHING`, and the last assertion reddens.
    root = initialised(tmp_path)
    (root / CONFIG_FILE).unlink()
    count = len(Manifest.read(root).records)
    report = _uninstall(root, tmp_path)
    assert report.note == NO_CONFIG.format(count=count)
    assert not (root / MANIFEST_PATH).exists() and (root / "AGENTS.md").is_file()
    with pytest.raises(Refusal, match=re.escape(NOTHING)):
        _uninstall(root, tmp_path)


@needs_git
def test_a_committed_path_and_record_reach_only_bytes_the_same_commit_states(
    tmp_path: Path,
) -> None:
    # Where the anchor ends. Artifact ids and the targets this build could write are the build's;
    # the `[paths]` value a target comes from and the digest a record carries are committed. A
    # commit pointing `roadmap` at README.md and recording README.md's exact bytes has uninstall
    # remove it, as its own diff could have. A byte of the file that commit does not state stops
    # it. Mutation (oracle): the engine's retired-digest comparison always matches -> the edited
    # README.md is removed and this reddens.
    for name, edit in (("stated", ""), ("edited", "a local line\n")):
        root = initialised(tmp_path / name)
        config = root / CONFIG_FILE
        config.write_text(
            config.read_text(encoding="utf-8") + '\n[paths]\nroadmap = "README.md"\n',
            encoding="utf-8",
        )
        manifest = Manifest.read(root)
        record = manifest.get("roadmap")
        assert record is not None
        forged = replace(record, target="README.md", sha256=digest(BEFORE))
        manifest.with_record(forged).write(root)
        readme = root / "README.md"
        readme.write_text(BEFORE + edit, encoding="utf-8")
        _uninstall(root, tmp_path / name)
        assert readme.exists() is bool(edit)


@needs_git
def test_a_symlinked_keelline_directory_is_refused_before_anything_is_written(
    tmp_path: Path,
) -> None:
    # A clone can commit `.keelline` as a symlink to a directory holding a manifest of its own.
    # The manifest is read through `contained()`, which refuses a path through a symlink, so the
    # run stops before any write, in the repository or where the link points.
    root = initialised(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    (root / ".keelline").rename(elsewhere)
    (root / ".keelline").symlink_to(elsewhere, target_is_directory=True)
    before, outside = snapshot(root), snapshot(elsewhere)
    with pytest.raises(Refusal, match="symlink"):
        _uninstall(root, tmp_path)
    assert_snapshot_unchanged(root, before)
    assert_snapshot_unchanged(elsewhere, outside)


@needs_git
def test_a_force_path_in_another_case_forces_nothing(tmp_path: Path) -> None:
    # A path is compared exactly. On a filesystem that folds case `agents.md` opens the same file
    # as `AGENTS.md`, and it still forces neither the region nor the skeleton.
    root = initialised(tmp_path)
    agents = root / "AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    edited = text.replace(
        "<!-- keelline:harness:begin -->\n", "<!-- keelline:harness:begin -->\nOur line.\n"
    )
    agents.write_text(edited, encoding="utf-8")
    _uninstall(root, tmp_path, force=("agents.md",))
    assert agents.read_text(encoding="utf-8") == edited


@needs_git
def test_a_repository_keelline_never_initialised_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "bare"
    root.mkdir()
    with pytest.raises(Refusal, match=re.escape(NOTHING)):
        _uninstall(root, tmp_path)


@needs_git
def test_a_harness_directory_a_person_made_stays_when_its_rule_goes(tmp_path: Path) -> None:
    # Mutation (oracle, advisory): drop the `marker_dirs` skip in `_prune` -> `.claude/` is
    # removed with the rule inside it, and the first assertion reddens.
    root = initialised(tmp_path)
    (root / ".claude").mkdir()
    config = root / CONFIG_FILE
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "[keelline]\n", '[keelline]\nprofile = "python"\n', 1
        ),
        encoding="utf-8",
    )
    upgrade(root, machine=tmp_path / "absent.toml", runner=LsRemote(), dry_run=False, force=())
    rules = root / ".claude" / "rules"
    assert any(rules.iterdir())
    _uninstall(root, tmp_path)
    assert (root / ".claude").is_dir() and not rules.exists()


@needs_git
def test_a_workflow_the_mode_no_longer_renders_still_goes(tmp_path: Path) -> None:
    # `upgrade` keeps a workflow `uvx` merely does not render; `uninstall` asks where this build
    # could have written it, and nothing else. Measured before: the workflow was left, unlisted,
    # beside a deleted manifest, and counted as an artifact this Keelline does not produce.
    listing = LsRemote(stdout=f"{'a' * 40}\trefs/tags/v{keelline.__version__}\n", code=0)
    root = initialised(tmp_path, runner=listing, ci=True)
    config = root / CONFIG_FILE
    config.write_text(
        config.read_text(encoding="utf-8").replace("[ci]\n", '[ci]\nmode = "uvx"\n'),
        encoding="utf-8",
    )
    report = _uninstall(root, tmp_path)
    assert not (root / ".github").exists() and report.orphans == 0


@needs_git
def test_a_directory_where_the_assessment_belongs_is_left_and_the_ledger_still_goes(
    tmp_path: Path,
) -> None:
    # A clone can commit a directory at `.keelline/assessment.json`. Unlinking it fails, and a
    # refusal there, after `keelline.toml` went, would leave every later run refusing before the
    # manifest. It is left behind with `.keelline/` around it, and the run finishes.
    # Mutation (advisory): drop the directory check in `_remove_ledger` -> the run refuses with
    # "cannot be removed" and the manifest stays, and this reddens at the call.
    root = initialised(tmp_path)
    committed = root / ".keelline" / "assessment.json"
    committed.mkdir()
    (committed / "theirs.md").write_text("theirs\n", encoding="utf-8")
    _uninstall(root, tmp_path)
    assert (committed / "theirs.md").is_file()
    assert tree(root) == {
        "README.md",
        ".keelline",
        ".keelline/assessment.json",
        ".keelline/assessment.json/theirs.md",
    }
