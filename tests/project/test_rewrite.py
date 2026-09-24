"""`rewrite_owned`: a tool-owned key moved, and the `config` record kept honest about it."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import keelline
from keelline.config.loader import CONFIG_FILE
from keelline.errors import Refusal
from keelline.project import rewrite as module
from keelline.project.rewrite import NO_DOCUMENT, rewrite_owned
from keelline.scaffold import MANIFEST_PATH, Manifest, digest
from tests.gitfixture import needs_git
from tests.project.repos import initialised

MOVED = {("keelline", "version"): "9.9.9"}


def _record_digest(root: Path) -> str:
    record = Manifest.read(root).get("config")
    assert record is not None
    return record.sha256


@needs_git
def test_an_untouched_document_is_restamped_with_its_new_bytes(tmp_path: Path) -> None:
    root = initialised(tmp_path)
    rewrite_owned(root, MOVED)
    text = (root / CONFIG_FILE).read_text(encoding="utf-8")
    assert 'version = "9.9.9"' in text
    assert _record_digest(root) == digest(text)


@needs_git
def test_an_edited_document_is_rewritten_and_its_record_never_blesses_the_edit(
    tmp_path: Path,
) -> None:
    root = initialised(tmp_path)
    path = root / CONFIG_FILE
    path.write_text(path.read_text(encoding="utf-8") + "# a note of ours\n", encoding="utf-8")
    stamped = _record_digest(root)
    rewrite_owned(root, MOVED)
    assert "# a note of ours\n" in path.read_text(encoding="utf-8")
    assert _record_digest(root) == stamped


@needs_git
def test_a_run_interrupted_between_its_two_writes_converges_on_the_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The record is written first. Interrupted there, nothing changed; interrupted after it, the
    # record names bytes the next run writes. Written the other way round, an interruption after
    # the document leaves a record no run will re-stamp, and `uninstall` keeps the file for good.
    root = initialised(tmp_path)
    original = Manifest.write

    def interrupted(self: Manifest, where: Path) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(Manifest, "write", interrupted)
    with pytest.raises(OSError):
        rewrite_owned(root, MOVED)
    monkeypatch.setattr(Manifest, "write", original)
    rewrite_owned(root, MOVED)
    assert _record_digest(root) == digest((root / CONFIG_FILE).read_text(encoding="utf-8"))


@needs_git
def test_nothing_to_move_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A promotion of a gate already enforced, or an upgrade with nothing to move, must not
    # rewrite identical bytes. Mutation (advisory): drop the early return -> this reddens.
    root = initialised(tmp_path)

    def refuse(*args: object) -> None:
        raise AssertionError("wrote a document that did not change")

    monkeypatch.setattr(module, "write_within", refuse)
    rewrite_owned(root, {("keelline", "version"): keelline.__version__})


def test_a_missing_document_is_a_refusal(tmp_path: Path) -> None:
    with pytest.raises(Refusal, match=NO_DOCUMENT):
        rewrite_owned(tmp_path, MOVED)


def test_a_hand_written_document_with_no_manifest_and_no_keelline_table_gets_the_key(
    tmp_path: Path,
) -> None:
    # `init` adopting a hand-written `keelline.toml` writes the tool-owned keys into it before any
    # manifest exists, and such a file may have no `[keelline]` table at all. Nothing is
    # re-stamped, because nothing is recorded yet, and no manifest is created.
    written = '[project]\nname = "widget"\n'
    (tmp_path / CONFIG_FILE).write_text(written, encoding="utf-8")
    rewrite_owned(tmp_path, MOVED)
    text = (tmp_path / CONFIG_FILE).read_text(encoding="utf-8")
    assert text.startswith(written)
    assert tomllib.loads(text) == {"project": {"name": "widget"}, "keelline": {"version": "9.9.9"}}
    assert not (tmp_path / MANIFEST_PATH).exists()
