"""The release's record of the files the harness executes without Python (§5.9, DC5).

Kept true on every commit and not only at a tag: `release check` compares the record to
the tree, so a change to the wrapper that forgot to re-record fails CI. `doctor files`
compares the INSTALLED copies to the INSTALLED record; a determined attacker who edits
both is not this check's threat — tag protection and the pinned SHA are (D16). Post-install
modification, a broken checkout, a partial update: those are.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from keelline import fsops
from keelline.errors import Failure

# The three files the harness runs on its own, with no interpreter of ours in front of them:
# the wrapper every hook entry executes, the entry table that names it, and the launcher the
# wrapper hands control to. Python files are not here — a wheel's contents are the packaging
# tool's to attest, and `check_artifacts.py` is what looks at those.
HASHED_FILES = ("hooks/run-hook.sh", "hooks/hooks.json", "scripts/keelline")
# Beside what it hashes, so an installation that carried the files carries the record too.
RECORD = "hooks/hashes.json"
FORMAT = 1


class UnreadableRecord(Failure):
    """The record is there and is not a record: a distinct answer from "absent", because an
    absent record skips in `doctor` while an unreadable one must be red."""


def digests(root: Path) -> dict[str, str]:
    """sha256 per hashed file that exists under `root`, in `HASHED_FILES` order."""
    found: dict[str, str] = {}
    for relative in HASHED_FILES:
        path = root / relative
        if path.is_file():
            found[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def read_record(root: Path) -> dict[str, str] | None:
    """The digests the record names, `None` when there is no record at all.

    The two are different answers and the callers branch on the difference: a build with no
    record is one `doctor` skips, and a record that is present and is not a record is one it
    must be red about.

    **The keys are repository-authored and are validated here as shape and never as trust.**
    A caller that prints one prints bytes the record's author chose: the record is read from
    an installed plugin root, which `doctor.checks.plugin_root` explains a committed
    `.claude/settings.json` `env` block can name. Holding the keys to `HASHED_FILES` here is
    the rule this function must NOT apply — `doctor._files` walks the union of the record and
    this build's own list precisely so that a record naming a file this build does not ship is
    visible rather than dropped, and `drift` reports the same direction — so the rule belongs
    where the printing happens: `_files` prints the names it knows and counts the rest.
    """
    path = root / RECORD
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UnreadableRecord(f"{RECORD} is not valid JSON: {exc}") from None
    files = document.get("files") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("format") != FORMAT
        or not isinstance(files, dict)
        or not all(isinstance(value, str) for value in files.values())
    ):
        raise UnreadableRecord(f"{RECORD} is present and is not a format-{FORMAT} record")
    return {str(key): str(value) for key, value in files.items()}


def write_record(root: Path) -> None:
    """Record every shipped file, or refuse: a partial record is not a record of a release.

    Not because a partial record would read as clean — both readers walk `HASHED_FILES` and
    would flag the file it omits. It is refused because the alternative is a record that says
    "these are the files the release shipped" while naming two of three, so every reader of it
    afterwards is reporting drift against a claim nobody meant to make. The failure belongs at
    the moment of writing, where the tree that is missing a file can still be fixed.
    """
    found = digests(root)
    if len(found) != len(HASHED_FILES):
        missing = [name for name in HASHED_FILES if name not in found]
        raise Failure(
            f"cannot record a release without {', '.join(missing)}; the record must name "
            "every shipped file"
        )
    body = json.dumps({"format": FORMAT, "files": found}, indent=2, sort_keys=True) + "\n"
    fsops.write_within(root, RECORD, body)


def drift(root: Path) -> list[str]:
    """Every way the tree and the record disagree, in the reader's own words.

    Both directions on purpose: a file the record names and the tree lacks is drift, and so is
    one whose bytes moved. A walk over the record alone would call a deleted file a match.
    """
    recorded = read_record(root)
    if recorded is None:
        return [f"{RECORD} is missing; run `keelline release hashes`"]
    actual = digests(root)
    problems = [
        f"{RECORD} names {name}, which is not in the tree"
        for name in recorded
        if name not in actual
    ]
    problems += [
        f"{RECORD} does not match {name}; run `keelline release hashes`"
        for name in actual
        if recorded.get(name) != actual[name]
    ]
    return problems
