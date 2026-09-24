"""The ledger of what Keelline last wrote under `.keelline/local/artifacts/`, and the engine rules
that read it: an unedited copy follows a changed template, a copy whose id left `[artifacts]
local` is retired, and a ledger a clone wrote reaches nothing but bytes it already names."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from keelline.scaffold import engine
from keelline.scaffold.engine import apply, plan
from keelline.scaffold.local import LOCAL_DIGESTS, MAX_BYTES, LocalDigests
from keelline.scaffold.manifest import Manifest, digest
from keelline.scaffold.model import Verb
from tests.scaffold.test_engine import a_config, a_template

LOCAL = ".keelline/local/artifacts/AGENTS.md"
OTHER = ".keelline/local/artifacts/other.md"


def _written(tmp_path: Path, render: str = "BODY\n") -> None:
    """`agents-md` written kept out of git, rendering `render`."""
    config = a_config(tmp_path, local=("agents-md",))
    apply(tmp_path, plan(tmp_path, config, [a_template(render=lambda: render)]))


def _ledger(tmp_path: Path, artifacts: object, **extra: object) -> None:
    path = tmp_path / LOCAL_DIGESTS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"format": 1, "artifacts": artifacts, **extra}), encoding="utf-8")


def test_a_write_kept_out_of_git_is_recorded_in_the_ledger_and_never_in_the_manifest(
    tmp_path: Path,
) -> None:
    _written(tmp_path)
    assert LocalDigests.read(tmp_path).entries == {"agents-md": (LOCAL, digest("BODY\n"))}
    assert Manifest.read(tmp_path).records == {}


def test_a_footprint_with_nothing_kept_out_of_git_writes_no_ledger(tmp_path: Path) -> None:
    apply(tmp_path, plan(tmp_path, a_config(tmp_path), [a_template()]))
    assert not (tmp_path / ".keelline" / "local").exists()


def test_an_unedited_copy_follows_a_changed_template(tmp_path: Path) -> None:
    # With the render as the only oracle, every unedited copy read as somebody's after a release
    # changed its template: `skip_modified`, and `uninstall` refused over it. The ledger says
    # these are the bytes Keelline wrote. Mutation (oracle): "an unedited artifact kept out of git
    # is skipped as not Keelline's once its template changes" -> the verb is `skip_modified`.
    _written(tmp_path)
    config = a_config(tmp_path, local=("agents-md",))
    planned = plan(tmp_path, config, [a_template(render=lambda: "BODY 2\n")])
    assert [(a.verb, a.reason) for a in planned.actions] == [(Verb.UPDATE, "refreshed")]
    apply(tmp_path, planned)
    assert (tmp_path / LOCAL).read_text(encoding="utf-8") == "BODY 2\n"
    assert LocalDigests.read(tmp_path).entries == {"agents-md": (LOCAL, digest("BODY 2\n"))}


def test_a_retired_unedited_copy_goes_after_its_template_changed(tmp_path: Path) -> None:
    # Mutation (oracle): "the ledger never vouches for bytes Keelline wrote kept out of git" ->
    # the copy is listed as changed and stays.
    _written(tmp_path)
    config = a_config(tmp_path, local=("agents-md",))
    retired = a_template(retired=True, render=lambda: "BODY 2\n")
    planned = plan(tmp_path, config, [retired])
    assert [(a.verb, a.target, a.reason) for a in planned.actions] == [
        (Verb.REMOVE, LOCAL, "retired")
    ]
    apply(tmp_path, planned)
    assert not (tmp_path / LOCAL).exists()
    # The last entry gone, the ledger goes with it.
    assert not (tmp_path / LOCAL_DIGESTS).exists()


def test_an_edited_copy_is_named_as_changed_and_with_no_ledger_as_unrecorded(
    tmp_path: Path,
) -> None:
    # Neither reason calls the file edited unless the ledger shows Keelline wrote other bytes
    # there. With the ledger gone the file is judged by the render alone, as before it existed.
    _written(tmp_path)
    (tmp_path / LOCAL).write_text("BODY\nours\n", encoding="utf-8")
    config = a_config(tmp_path, local=("agents-md",))
    changed = plan(tmp_path, config, [a_template()])
    assert [(a.verb, a.reason) for a in changed.actions] == [
        (Verb.SKIP_MODIFIED, engine.CHANGED_LOCALLY)
    ]
    (tmp_path / LOCAL_DIGESTS).unlink()
    (tmp_path / LOCAL).write_text("BODY\n", encoding="utf-8")
    assert plan(tmp_path, config, [a_template()]).unchanged == ("agents-md",)
    unrecorded = plan(tmp_path, config, [a_template(render=lambda: "BODY 2\n")])
    assert [(a.verb, a.reason) for a in unrecorded.actions] == [
        (Verb.SKIP_MODIFIED, engine.NOT_OURS_LOCALLY)
    ]


def test_a_copy_whose_id_left_the_list_is_retired_while_its_bytes_are_keellines(
    tmp_path: Path,
) -> None:
    # Nothing ever judged it again: `upgrade` created the committed file and left the copy, and
    # `uninstall` refused over it for good with a `--force` no action could reach. Mutation
    # (oracle): "a copy left kept out of git when its id left [artifacts] local is never judged"
    # -> the plan holds the create alone.
    _written(tmp_path)
    config = a_config(tmp_path)
    planned = plan(tmp_path, config, [a_template(render=lambda: "BODY 2\n")])
    assert [(a.verb, a.target, a.reason) for a in planned.actions] == [
        (Verb.REMOVE, LOCAL, "relocated"),
        (Verb.CREATE, "AGENTS.md", "new"),
    ]
    apply(tmp_path, planned)
    assert not (tmp_path / LOCAL).exists() and (tmp_path / "AGENTS.md").is_file()
    assert LocalDigests.read(tmp_path).entries == {}


def test_a_changed_copy_whose_id_left_the_list_is_named_and_force_takes_it(
    tmp_path: Path,
) -> None:
    _written(tmp_path)
    (tmp_path / LOCAL).write_text("BODY\nours\n", encoding="utf-8")
    config = a_config(tmp_path)
    planned = plan(tmp_path, config, [a_template()])
    assert [(a.verb, a.target, a.reason) for a in planned.actions] == [
        (Verb.SKIP_MODIFIED, LOCAL, engine.LEFT_LOCALLY),
        (Verb.CREATE, "AGENTS.md", "new"),
    ]
    forced = plan(tmp_path, config, [a_template()], force=(LOCAL,))
    assert [(a.verb, a.target, a.reason) for a in forced.actions] == [
        (Verb.REMOVE, LOCAL, "relocated, forced"),
        (Verb.CREATE, "AGENTS.md", "new"),
    ]


def test_a_ledger_entry_reaches_only_the_artifact_s_own_place(tmp_path: Path) -> None:
    # A clone can force-add the ledger. An entry naming another file under the directory, with
    # that file's exact digest, must not make it this artifact's copy: `local_copy` accepts the
    # template's own target under `LOCAL_ARTIFACTS` and nothing else. Mutation (oracle): "a
    # ledger entry names which file kept out of git is an artifact's copy" -> `other.md` is
    # removed.
    other = tmp_path / OTHER
    other.parent.mkdir(parents=True)
    other.write_text("BODY\n", encoding="utf-8")
    _ledger(tmp_path, {"agents-md": {"target": OTHER, "sha256": digest("BODY\n")}})
    planned = plan(tmp_path, a_config(tmp_path), [a_template()])
    assert [(a.verb, a.target) for a in planned.actions] == [(Verb.CREATE, "AGENTS.md")]
    apply(tmp_path, planned)
    assert other.is_file()


@pytest.mark.parametrize(
    ("artifacts", "extra"),
    [
        # Outside `LOCAL_ARTIFACTS`: a committed file, attach's ledger, a parent segment.
        ({"agents-md": {"target": "AGENTS.md", "sha256": "0" * 64}}, {}),
        ({"agents-md": {"target": ".keelline/local/attach.json", "sha256": "0" * 64}}, {}),
        ({"agents-md": {"target": ".keelline/local/artifacts/../x", "sha256": "0" * 64}}, {}),
        # Not this module's shape.
        ({"agents-md": {"target": LOCAL, "sha256": "zz"}}, {}),
        ({"Agents\x1b[31m": {"target": LOCAL, "sha256": "0" * 64}}, {}),
        ({"agents-md": [LOCAL, "0" * 64]}, {}),
        ([], {}),
        ({"agents-md": {"target": LOCAL, "sha256": "0" * 64}}, {"format": 2}),
    ],
)
def test_a_ledger_that_is_not_exactly_this_shape_is_absent(
    tmp_path: Path, artifacts: object, extra: dict[str, object]
) -> None:
    # A fault anywhere makes the whole ledger absent, which only sends the engine back to the
    # render rule. Mutation (oracle): "a ledger entry may name a file outside the artifacts
    # directory" -> the first two cases read as entries.
    _ledger(tmp_path, artifacts, **extra)
    assert LocalDigests.read(tmp_path).entries == {}


def test_an_oversized_unparsable_or_redirected_ledger_is_absent(tmp_path: Path) -> None:
    path = tmp_path / LOCAL_DIGESTS
    path.parent.mkdir(parents=True)
    entry = {"agents-md": {"target": LOCAL, "sha256": "0" * 64}}
    body = json.dumps({"format": 1, "artifacts": entry})
    path.write_text(body + " " * MAX_BYTES, encoding="utf-8")
    assert LocalDigests.read(tmp_path).entries == {}
    path.write_text("{" * 100_000, encoding="utf-8")
    assert LocalDigests.read(tmp_path).entries == {}
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text(body, encoding="utf-8")
    path.unlink()
    path.symlink_to(elsewhere)
    assert LocalDigests.read(tmp_path).entries == {}
    path.unlink()
    os.mkfifo(path)
    assert LocalDigests.read(tmp_path).entries == {}
    path.unlink()
    path.write_text(body, encoding="utf-8")
    assert LocalDigests.read(tmp_path).entries == {"agents-md": (LOCAL, "0" * 64)}
