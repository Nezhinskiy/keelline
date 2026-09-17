"""Where the dispatcher's markers and diagnostics survive between invocations (§5.3).

Two of the three path segments below are payload-controlled — the marker key a handler chose,
and the session id off the hook's stdin — so both are hashed to a fixed-width hex name, and
every write and removal still goes through `fsops`' `O_NOFOLLOW` walk. Two controls rather
than one, because what runs here is not only a write but a `remove_within` loop, and D14
permits it in exactly one directory.

Nothing here ever raises at its caller. A hook runs on every tool call, so an unwritable
`${CLAUDE_PLUGIN_DATA}` must cost a lost marker and never a refused Bash command — which is
the degradation `NullSink`'s own docstring already promises, reached here by returning one.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from keelline.fsops import UnsafePath, open_within, remove_within, write_within
from keelline.hooks.api import NullSink, Sink

# The one directory Keelline owns inside the data root the harness handed it.
DIRECTORY = "keelline"
MARKERS = "markers"
DIAGNOSTICS = "diagnostics.jsonl"
ROTATED = "diagnostics.1.jsonl"
# Written once, by `sink_for`, to find out whether this data root can be written at all. A
# probe rather than a `try` around the first real write: the first real write is a marker, and
# losing it silently is exactly what the sink exists to stop.
PROBE = ".probe"
# Per FIELD, before serialisation. A record holds a stable reason string, not a payload; 2,000
# characters is generous for that and small enough that a pathological handler cannot fill a
# disk one line at a time. Capping the serialised line instead would cut inside whichever field
# sorts first and leave `doctor` a record it cannot parse.
DIAGNOSTIC_FIELD_CHARS = 2_000
DIAGNOSTICS_MAX_BYTES = 256 * 1024
MARKER_SESSIONS_KEPT = 50
# A session id the payload did not carry. `parse_event` types `session_id` as `str | None`, and
# every such invocation shares this one segment: markers stop being per-session, which is a
# weaker guarantee than the harness gives and the honest name for it.
UNKEYED_SESSION = ""


def _segment(value: str) -> str:
    """One payload-controlled string, as one fixed-width path segment.

    `../../escape` as a filename is a write — and a delete — outside the one directory D14
    permits. The hash also fixes the length, so a value of any size costs one short name.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _rmdir_within(root: Path, target: str) -> None:
    """`remove_within` for a directory, which unlinks and therefore cannot remove one.

    Not a second writer and not a widening of `fsops`: it is `remove_within`'s own body with
    `os.rmdir` in place of `os.unlink`, reached through the same `open_within` walk, so the
    removal happens relative to a descriptor no symlink can redirect. It lives here rather than
    in `fsops` because this is the only directory anything removes — D14 permits a removal loop
    in exactly one place, and that place is the marker tree below.
    """
    with open_within(root, target) as (dir_fd, name), contextlib.suppress(FileNotFoundError):
        os.rmdir(name, dir_fd=dir_fd)


@dataclass(frozen=True)
class DataSink:
    root: Path
    session: str

    def _target(self, key: str) -> str:
        return f"{MARKERS}/{_segment(self.session)}/{_segment(key)}"

    def seen(self, key: str) -> bool:
        return (self.root / self._target(key)).exists()

    def mark(self, key: str) -> None:
        try:
            write_within(self.root, self._target(key), "")
            self._prune()
        except (OSError, UnsafePath):
            return None

    def _prune(self) -> None:
        """Bound the marker tree, newest first.

        Sessions are unbounded in number and a marker is worthless once its session ends, so
        without this the directory grows for the life of the machine. This session's own
        directory was just written, so it is the newest by this ordering and is never the one
        dropped — which is what makes pruning safe to do on the write path.

        `st_mtime_ns` rather than `st_mtime`: the float carries roughly a quarter-microsecond
        at present-day epochs, which is finer than two directories can be created, but the
        integer costs nothing and cannot be argued about.
        """
        base = self.root / MARKERS
        try:
            sessions = sorted(
                (path for path in base.iterdir() if path.is_dir()),
                key=lambda path: path.stat().st_mtime_ns,
                reverse=True,
            )
        except OSError:
            return None
        for stale in sessions[MARKER_SESSIONS_KEPT:]:
            for child in stale.iterdir():
                remove_within(self.root, f"{MARKERS}/{stale.name}/{child.name}")
            _rmdir_within(self.root, f"{MARKERS}/{stale.name}")

    def diagnostic(self, record: dict[str, object]) -> None:
        # The session is capped with everything else, and not merged in past the cap. It comes
        # off the hook's stdin and `parse_event` type-checks it as `str` and nothing more, so it
        # is as payload-controlled as any field a handler supplies — "never raw stdin" (§5.3)
        # covers the key this record is filed under as much as it covers the reason string.
        capped = {
            key: value[:DIAGNOSTIC_FIELD_CHARS] if isinstance(value, str) else value
            for key, value in {"session": self.session, **record}.items()
        }
        line = json.dumps(capped, default=str, sort_keys=True)
        payload = (line + "\n").encode("utf-8")
        try:
            with open_within(self.root, DIAGNOSTICS) as (dir_fd, name):
                self._rotate(dir_fd, name, len(payload))
                handle = os.open(
                    name,
                    os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=dir_fd,
                )
                try:
                    os.write(handle, payload)
                finally:
                    os.close(handle)
        except (OSError, UnsafePath):
            return None

    def _rotate(self, dir_fd: int, name: str, incoming: int) -> None:
        """Keep one generation, both halves on the descriptor the contained walk opened.

        `os.stat` and `os.rename` relative to `dir_fd`, never by path: re-resolving the name
        between the size check and the rename is the window the walk exists to close.
        """
        try:
            size = os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_size
        except FileNotFoundError:
            return None
        if size + incoming <= DIAGNOSTICS_MAX_BYTES:
            return None
        os.rename(name, ROTATED, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)


def sink_for(session: str | None, env: Mapping[str, str]) -> Sink:
    """A durable sink under the harness's data root, or `NullSink()` when there is not one.

    `PLUGIN_DATA` is Codex's name for the same thing (S1), so one lookup serves both harnesses.
    The data root itself belongs to the harness and is not created here; `keelline/` under it is
    ours, and is created by the probe through `write_within`'s contained walk rather than by a
    `mkdir(parents=True)` that would follow a symlink on the way.
    """
    data = env.get("CLAUDE_PLUGIN_DATA") or env.get("PLUGIN_DATA")
    if not data:
        return NullSink()
    base = Path(data)
    try:
        write_within(base, f"{DIRECTORY}/{PROBE}", "")
    except (OSError, UnsafePath):
        return NullSink()
    return DataSink(
        root=base / DIRECTORY, session=session if session is not None else UNKEYED_SESSION
    )
