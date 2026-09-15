from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from keelline.fsops import (
    NEW_FILE_MODE,
    UnsafePath,
    _mode_of,
    mkdirs_within,
    open_within,
    remove_within,
    write_atomically,
    write_atomically_at,
    write_within,
)


def _umasked(mode: int = NEW_FILE_MODE) -> int:
    """`mode` as the kernel will actually create it under this process's umask.

    The suite must not assert `0o644` outright: forcing that mode is the defect N2 named, and a
    test that pins the forced value passes only because the machine running it happens to use
    `umask 022`. Read once and restored immediately — `os.umask` is a set-and-return.
    """
    current = os.umask(0o077)
    os.umask(current)
    return mode & ~current


def test_a_new_file_is_written_with_the_default_mode(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b.txt"
    write_atomically(target, "body\n")
    assert target.read_text(encoding="utf-8") == "body\n"
    assert stat.S_IMODE(target.stat().st_mode) == _umasked()


def test_a_new_file_does_not_override_the_umask(tmp_path: Path) -> None:
    # A trust record written under `umask 077` landed 0o644 — a world-readable security record
    # in `~/.config`, because the mode was forced onto the descriptor rather than requested of
    # the kernel. The machine owner's umask is a decision, not a default to be overridden.
    previous = os.umask(0o077)
    try:
        target = tmp_path / "private.json"
        write_atomically(target, "{}\n")
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    finally:
        os.umask(previous)


def test_an_existing_file_keeps_its_mode(tmp_path: Path) -> None:
    target = tmp_path / "b.txt"
    target.write_text("old\n", encoding="utf-8")
    os.chmod(target, 0o640)
    write_atomically(target, "new\n")
    assert target.read_text(encoding="utf-8") == "new\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_no_temporary_file_survives(tmp_path: Path) -> None:
    write_atomically(tmp_path / "b.txt", "body\n")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b.txt"]


def test_a_failed_write_leaves_the_original_and_no_temporary(tmp_path: Path) -> None:
    target = tmp_path / "b.txt"
    target.write_text("original\n", encoding="utf-8")

    with pytest.raises(UnicodeEncodeError):
        write_atomically(target, "\udcff")
    assert target.read_text(encoding="utf-8") == "original\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b.txt"]


# --- the descriptor walk, which had no coverage at all ---------------------------------------
#
# `open_within` is what the module leads with, and `write_atomically_at` is the sole write path
# of the scaffold engine. Neither was exercised by any test, which is how a call that raises
# NotImplementedError on Linux passed a green suite on macOS: the platform difference only
# shows where the code actually runs.


def test_a_symlinked_component_fails_the_open(tmp_path: Path) -> None:
    (tmp_path / "outside").mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "docs").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(UnsafePath), open_within(root, "docs/a.md"):
        pass


def test_a_component_that_is_not_a_directory_fails_the_open(tmp_path: Path) -> None:
    (tmp_path / "docs").write_text("a file, not a directory\n", encoding="utf-8")
    with pytest.raises(UnsafePath), open_within(tmp_path, "docs/a.md"):
        pass


def test_a_path_that_names_nothing_fails_the_open(tmp_path: Path) -> None:
    with pytest.raises(UnsafePath), open_within(tmp_path, ""):
        pass


def test_a_write_through_the_descriptor_lands_where_the_walk_ended(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    with open_within(tmp_path, "docs/a.md") as (dir_fd, name):
        write_atomically_at(dir_fd, name, "body\n")
    assert (tmp_path / "docs" / "a.md").read_text(encoding="utf-8") == "body\n"
    assert stat.S_IMODE((tmp_path / "docs" / "a.md").stat().st_mode) == _umasked()


def test_a_descriptor_write_keeps_the_mode_of_the_file_it_replaced(tmp_path: Path) -> None:
    target = tmp_path / "a.md"
    target.write_text("old\n", encoding="utf-8")
    os.chmod(target, 0o640)
    with open_within(tmp_path, "a.md") as (dir_fd, name):
        write_atomically_at(dir_fd, name, "new\n")
    assert target.read_text(encoding="utf-8") == "new\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_no_temporary_survives_a_descriptor_write(tmp_path: Path) -> None:
    with open_within(tmp_path, "a.md") as (dir_fd, name):
        write_atomically_at(dir_fd, name, "body\n")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.md"]


def test_a_failed_descriptor_write_leaves_the_original_and_no_temporary(tmp_path: Path) -> None:
    target = tmp_path / "a.md"
    target.write_text("original\n", encoding="utf-8")
    with pytest.raises(UnicodeEncodeError), open_within(tmp_path, "a.md") as (dir_fd, name):
        write_atomically_at(dir_fd, name, "\udcff")
    assert target.read_text(encoding="utf-8") == "original\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.md"]


def test_a_symlinked_target_does_not_propagate_its_mode(tmp_path: Path) -> None:
    # `lstat` on a symlink reports 0o777. `contained()` refuses a symlink at the final
    # component before any caller reaches here, so this is a floor under a guard one caller
    # away — asserted because the guard and the floor live in different modules. `None` is
    # "carry nothing over", which is what sends the write down the umask path.
    (tmp_path / "elsewhere").write_text("x\n", encoding="utf-8")
    (tmp_path / "a.md").symlink_to(tmp_path / "elsewhere")
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert _mode_of(fd, "a.md") is None
    finally:
        os.close(fd)


def test_an_absent_file_carries_no_mode(tmp_path: Path) -> None:
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert _mode_of(fd, "missing.md") is None
    finally:
        os.close(fd)


# --- containment, which the twelve tests above did not test -----------------------------------
#
# The walk refused symlinks and nothing else. `PurePosixPath(relative).parts` keeps `..` and
# reports a leading `/` as its own first part, and `openat` ignores its `dir_fd` for an absolute
# path — so `open_within(root, "../outside/victim.txt")` handed back a descriptor outside the
# root, and an absolute argument restarted the walk at `/`. On Linux, where `/etc` and `/var` are
# real directories, the absolute case completed; macOS refused it only because those two happen
# to be symlinks there. Grepping this file for `..` or `absolute` used to return nothing, and
# that absence is why it survived.


def test_a_parent_component_never_leaves_the_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text("mine\n", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(UnsafePath), open_within(root, "../outside/victim.txt"):
        pass
    assert (outside / "victim.txt").read_text(encoding="utf-8") == "mine\n"


def test_a_parent_component_anywhere_along_the_path_is_refused(tmp_path: Path) -> None:
    # Not only as the first component: `docs/../../outside` is the same escape spelled longer,
    # and the loop that refuses it has to look at every part rather than at `parts[0]`.
    (tmp_path / "docs").mkdir()
    with pytest.raises(UnsafePath), open_within(tmp_path, "docs/../../outside/victim.txt"):
        pass


def test_an_absolute_path_is_refused(tmp_path: Path) -> None:
    # `os.open` ignores `dir_fd` for an absolute path, so without this the walk restarts at the
    # filesystem root. This is the case that succeeds on Linux, where CI runs.
    #
    # `match=` and not a bare `raises`: with the explicit check deleted an absolute path is
    # still refused, by the empty-first-component rule — `"/etc".split("/")` starts with `""`.
    # So the assertion has to be about the *reason*, or a later edit to that other rule takes
    # the absolute case with it silently. `mutations.toml` records this; the oracle found it.
    with pytest.raises(UnsafePath, match="absolute"), open_within(tmp_path, "/etc/passwd"):
        pass


def test_a_current_directory_component_is_refused(tmp_path: Path) -> None:
    # `PurePosixPath` normalises `.` away today, so this asserts the guard rather than the
    # parse: the normalisation is pathlib's implementation detail and this is the single place
    # five later lanes' containment rests on.
    from keelline.fsops import _checked

    with pytest.raises(UnsafePath):
        _checked("docs/./a.md")


# --- the reusable write surface ---------------------------------------------------------------


def test_write_within_creates_the_parents_and_lands_inside_the_root(tmp_path: Path) -> None:
    write_within(tmp_path, "a/b/c.txt", "body\n")
    assert (tmp_path / "a" / "b" / "c.txt").read_text(encoding="utf-8") == "body\n"


def test_write_within_refuses_an_escaping_target(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(UnsafePath):
        write_within(tmp_path / "root", "../outside/victim.txt", "PWNED\n")
    assert not (outside / "victim.txt").exists()


def test_mkdirs_within_refuses_a_symlinked_component_with_nothing_created(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePath):
        mkdirs_within(root, "docs/deep/a.md")
    assert list(outside.iterdir()) == []


def test_remove_within_unlinks_and_tolerates_an_absent_file(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("body\n", encoding="utf-8")
    remove_within(tmp_path, "a.md")
    assert not (tmp_path / "a.md").exists()
    remove_within(tmp_path, "a.md")


def test_remove_within_refuses_an_escaping_target(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text("mine\n", encoding="utf-8")
    with pytest.raises(UnsafePath):
        remove_within(tmp_path / "root", "../outside/victim.txt")
    assert (outside / "victim.txt").exists()


# --- durability -------------------------------------------------------------------------------


def test_the_bytes_are_fsynced_before_the_rename(tmp_path: Path) -> None:
    # `os.replace` gives rename atomicity, which is the important property and was already
    # achieved; it does not give durability. After power loss the rename can be durable while
    # the data is not, leaving exactly the zero-length note the module docstring opens by
    # promising to prevent. The order is what the assertion is about: the file descriptor is
    # synced while the temporary still exists, the directory after the name is in place.
    calls: list[str] = []
    real_fsync = os.fsync
    real_replace = os.replace

    def spy_fsync(fd: int) -> None:
        calls.append("fsync")
        real_fsync(fd)

    def spy_replace(*args: object, **kwargs: object) -> None:
        calls.append("replace")
        real_replace(*args, **kwargs)  # type: ignore[arg-type]

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(os, "fsync", spy_fsync)
        monkey.setattr(os, "replace", spy_replace)
        write_atomically(tmp_path / "a.md", "body\n")
    finally:
        monkey.undo()
    assert calls == ["fsync", "replace", "fsync"]


def test_a_directory_that_cannot_be_fsynced_does_not_fail_a_written_file(tmp_path: Path) -> None:
    # The data is on disk and the rename has happened by the time the directory is synced, so a
    # filesystem that answers EINVAL there has cost this call its durability guarantee and
    # nothing else. Raising would report a successful write as a failed one.
    import errno as _errno

    real_fsync = os.fsync
    seen: list[int] = []

    def flaky_fsync(fd: int) -> None:
        seen.append(fd)
        if len(seen) > 1:
            raise OSError(_errno.EINVAL, "fsync on a directory is not supported here")
        real_fsync(fd)

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(os, "fsync", flaky_fsync)
        write_atomically(tmp_path / "a.md", "body\n")
    finally:
        monkey.undo()
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "body\n"
