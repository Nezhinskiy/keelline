"""Where artifacts kept out of git live, and the ledger of what Keelline last wrote there.

An `[artifacts] local` artifact lives under `LOCAL_ARTIFACTS`, a directory the footprint's ignore
block keeps out of git, and `.keelline/manifest.json` never records it: the manifest is committed,
and a record would put a machine's local state into every clone. With no record, the one oracle
for "Keelline's bytes" was what the running build renders. So once a release changed a template,
every unedited artifact kept out of git read as somebody's: `upgrade` skipped it and `uninstall`
refused over it. And a copy whose id had left `[artifacts] local` was never judged at all, so
`uninstall` refused over it for good, suggesting a `--force` that no planned action could reach.

`LocalDigests` is the record those runs lacked, kept where the artifacts are and never committed:
`LOCAL_DIGESTS`, under `LOCAL_ROOT` beside `LOCAL_ARTIFACTS` rather than inside it, so no
`[artifacts] local` target can land on it. The engine updates it in `apply` for every write and
removal of a file under `LOCAL_ARTIFACTS`, and `uninstall` removes it before the ignore block goes.

**It is read as untrusted, and it authorizes little.** The ignore block keeps it out of git, but a
clone can force-add any file, and a clone's checkout then carries it. So it is read bounded
(`MAX_BYTES`, `MAX_ENTRIES`), through the same `O_NOFOLLOW` walk writes use, shape-checked entry by
entry, and a fault anywhere makes the whole ledger absent: absence only sends the engine back to
the render rule, so it is never worth a refusal. Nothing in it is ever printed. An entry is
consulted only under the id of a template this build produced, only at that template's own place
under `LOCAL_ARTIFACTS`, and only to overwrite or remove a file there whose current bytes digest to
exactly what the entry records. That is the manifest's boundary — a committed record reaches only
bytes its committer already controls — and narrower: under `LOCAL_ARTIFACTS` a fresh clone holds
only what the clone itself force-added, and a file a person wrote there has bytes nobody else can
predict.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

from keelline.config.schema import PATH_VALUE
from keelline.errors import Refusal
from keelline.fsops import open_within, remove_within, write_within

LOCAL_ROOT = ".keelline/local"
# `[artifacts] local` artifacts live one directory further down, so no `[artifacts] local` entry
# can land one on a file another lane keeps under `LOCAL_ROOT`: attach's ledger, the local-only
# note store, and the ledger below. `PATH_VALUE` refuses a `..` segment, so for that setting the
# prefix is a boundary and not a convention; the anchor is this constant in the installed package.
# A `[paths]` value never reaches `.keelline/` at all: `config.paths.validate_paths` refuses one
# that names it.
LOCAL_ARTIFACTS = f"{LOCAL_ROOT}/artifacts"
LOCAL_DIGESTS = f"{LOCAL_ROOT}/artifacts.json"
FORMAT = 1
MAX_BYTES = 64 * 1024
MAX_ENTRIES = 256
GENERATED = (
    "Written by keelline: the bytes it last wrote for each artifact kept out of git. Never "
    "commit it; deleting it only makes later runs judge those files by what they render."
)
# An artifact id as this build spells them, bounded. An entry under any other id is a fault.
_ID = re.compile(r"\A[a-z0-9][a-z0-9._-]{0,63}\Z")
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)


def _read_bounded(root: Path) -> bytes | None:
    """At most `MAX_BYTES + 1` bytes of a regular file at `LOCAL_DIGESTS`, or `None`.

    Through `open_within`, so no component, the file included, is followed if it is a symlink,
    and `O_NONBLOCK` so a FIFO planted there cannot hang the run; anything but a regular file is
    absent.
    """
    try:
        with open_within(root, LOCAL_DIGESTS) as (dir_fd, name):
            handle = os.open(name, _READ_FLAGS, dir_fd=dir_fd)
            with os.fdopen(handle, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    return None
                return stream.read(MAX_BYTES + 1)
    except OSError:
        return None


def _entries(raw: bytes) -> dict[str, tuple[str, str]] | None:
    """The entries `raw` holds, or `None` for anything but exactly this module's own shape."""
    if len(raw) > MAX_BYTES:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        return None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        return None
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict) or len(artifacts) > MAX_ENTRIES:
        return None
    entries: dict[str, tuple[str, str]] = {}
    for artifact_id, entry in artifacts.items():
        if not isinstance(entry, dict) or not _ID.match(artifact_id):
            return None
        target, sha256 = entry.get("target"), entry.get("sha256")
        if not (
            isinstance(target, str)
            and isinstance(sha256, str)
            and target.startswith(f"{LOCAL_ARTIFACTS}/")
            and PATH_VALUE.match(target)
            and _SHA256.match(sha256)
        ):
            return None
        entries[artifact_id] = (target, sha256)
    return entries


@dataclass(frozen=True)
class LocalDigests:
    """Artifact id -> `(target, sha256)`: where Keelline last wrote it under `LOCAL_ARTIFACTS`,
    and the digest of its own part of that file, exactly as a manifest record stamps it."""

    entries: dict[str, tuple[str, str]] = field(default_factory=dict)

    @classmethod
    def read(cls, root: Path) -> LocalDigests:
        raw = _read_bounded(root)
        entries = None if raw is None else _entries(raw)
        return cls(entries or {})

    def target_of(self, artifact_id: str) -> str | None:
        entry = self.entries.get(artifact_id)
        return None if entry is None else entry[0]

    def matches(self, artifact_id: str, target: str, sha256: str) -> bool:
        """Whether the entry for `artifact_id` records `sha256` at `target`."""
        return self.entries.get(artifact_id) == (target, sha256)

    def with_entry(self, artifact_id: str, target: str, sha256: str) -> LocalDigests:
        return LocalDigests({**self.entries, artifact_id: (target, sha256)})

    def without(self, artifact_id: str) -> LocalDigests:
        return LocalDigests({k: v for k, v in self.entries.items() if k != artifact_id})

    def write(self, root: Path) -> None:
        """Replace the ledger through the `O_NOFOLLOW` walk, or remove it once it records nothing,
        and refuse rather than raise: this runs from `apply`'s `finally`, like the manifest."""
        try:
            if not self.entries:
                # A missing `.keelline/local/` is a ledger already gone, not a fault.
                with contextlib.suppress(FileNotFoundError):
                    remove_within(root, LOCAL_DIGESTS)
                return
            body = {
                "_generated": GENERATED,
                "format": FORMAT,
                "artifacts": {
                    artifact_id: {"target": target, "sha256": sha256}
                    for artifact_id, (target, sha256) in sorted(self.entries.items())
                },
            }
            write_within(root, LOCAL_DIGESTS, json.dumps(body, indent=2) + "\n")
        except OSError as exc:
            raise Refusal(f"{LOCAL_DIGESTS} cannot be written: {exc}") from exc
