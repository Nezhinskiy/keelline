"""One writer for every file Keelline replaces in place, and one way to reach it safely.

Two problems, one module.

*Atomicity.* A note, an index and a scaffolded artifact are each a file a person may be
editing, and a bare `write_text` truncates before it writes: a crash in between leaves an
empty file where the only copy of a note was. `mkstemp` plus `os.replace` makes the
replacement atomic, and the mode of the replaced file is carried over, because a fresh
temporary is 0600 and silently tightening `.gitignore`, `AGENTS.md` or a workflow file is a
defect of its own.

*Containment that survives the write.* Validating a path string and then writing to it leaves
a window in which a component can become a symlink, and the clone may be running a process of
its own. `open_within` walks the path one component at a time with `O_NOFOLLOW`, so a symlink
anywhere along it fails the open rather than redirecting it, and returns a directory
descriptor the write then happens relative to. The string is never resolved again.

A leaf module: it imports nothing from `keelline`, so the hook path pays no area import to
reach it.
"""

from __future__ import annotations

import contextlib
import errno
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

NEW_FILE_MODE = 0o644
_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


class UnsafePath(OSError):
    """A component of the path is a symlink, or is not a directory."""


@contextmanager
def open_within(root: Path, relative: str) -> Iterator[tuple[int, str]]:
    """Yield `(directory descriptor, final name)` for `root/relative`, following no symlink.

    The caller writes through the descriptor, so nothing between this walk and the write can
    redirect it: `os.replace(..., src_dir_fd=fd, dst_dir_fd=fd)` never re-resolves the parent.
    """
    parts = PurePosixPath(relative).parts
    if not parts:
        raise UnsafePath(f"{relative!r} names no file")
    fd = os.open(root, _DIR_FLAGS)
    opened = [fd]
    try:
        for part in parts[:-1]:
            try:
                nxt = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except OSError as exc:
                # O_NOFOLLOW on a symlink reports ELOOP on Linux and ENOTDIR on macOS when the
                # link points at a directory; both mean the same thing here.
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise UnsafePath(
                        f"{relative!r}: {part!r} is a symlink or not a directory"
                    ) from exc
                raise
            opened.append(nxt)
            fd = nxt
        yield fd, parts[-1]
    finally:
        for handle in reversed(opened):
            os.close(handle)


def _mode_of(dir_fd: int, name: str) -> int:
    try:
        return stat.S_IMODE(os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_mode)
    except FileNotFoundError:
        return NEW_FILE_MODE


def write_atomically_at(dir_fd: int, name: str, text: str, *, encoding: str = "utf-8") -> None:
    """Replace `name` inside the already-opened directory, keeping the mode it had."""
    mode = _mode_of(dir_fd, name)
    temporary = f".keelline-{os.getpid()}-{name}.tmp"
    handle = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=dir_fd)
    try:
        with os.fdopen(handle, "w", encoding=encoding) as stream:
            stream.write(text)
        os.chmod(temporary, mode, dir_fd=dir_fd, follow_symlinks=False)
        os.replace(temporary, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    except BaseException:
        _unlink_quietly(dir_fd, temporary)
        raise


def _unlink_quietly(dir_fd: int, name: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(name, dir_fd=dir_fd)


def write_atomically(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Replace `path` with `text` in one step, keeping the mode it already had.

    The plain-path form, for callers that already hold a trusted absolute path: the memory
    store's own notes and index, whose directory the resolver has already validated.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = NEW_FILE_MODE
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".keelline-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding=encoding) as stream:
            stream.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
