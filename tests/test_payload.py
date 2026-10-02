"""The plugin folder held to the file rules the Claude plugin directory checks at submission.

The payload is every path in `HEAD`'s tree, because the plugin folder is the repository root: the
marketplace's one plugin has `source` `./`, and `test_the_plugin_folder_is_the_repository_root`
reddens the day it moves, so that this walk changes with the move instead of going on passing over
the wrong tree. The tree and not the working tree, because the directory reads a commit: a local
edit, a line-ending conversion or a file deleted on disk is not what it scans.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

from tests.gitfixture import git, git_bytes, needs_git

ROOT = Path(__file__).resolve().parents[1]

# The directory's rules, as its pre-submission checklist states them
# (https://claude.com/docs/plugins/pre-submission-checklist, fetched 2026-10-02; the page carries
# no date), each with the result the page gives it: Held (the listing waits for a reviewer),
# Blocks, Validation stops, or, for a link, a submodule and a Git LFS pointer, "Blocks where the
# plugin loads the entry. Warning elsewhere." The plugin folder the rules apply to is the
# repository root, because the marketplace's `source` is `./`, so every rule below reads every path.
#
# Held: a file that is not an image or a font at `FILE_MAX_BYTES` or more, and more than
# `FILES_MAX` files.
FILE_MAX_BYTES = 256 * 1024
FILES_MAX = 512
# Held: a binary file other than the images and fonts the page names. It admits "text files, SVG
# included, complete PNG, JPEG, GIF, and WebP images, and font files" and names `.ico`, `.pdf`,
# `.zip` and compiled executables as held, so an `.ico` is not an image here. The same suffixes are
# the ones the size rule exempts.
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
FONT_SUFFIXES = (".woff", ".woff2", ".ttf", ".otf")
EXEMPT_SUFFIXES = IMAGE_SUFFIXES + FONT_SUFFIXES
# Binary is git's own test: a NUL byte in the first 8000 bytes (`buffer_is_binary`).
BINARY_PROBE_BYTES = 8000
# Blocks where loaded, Warning elsewhere: a symbolic link, a Git submodule (a gitlink entry) and a
# Git LFS pointer file. Any path here is one the plugin may load, so each is a finding wherever it
# is.
SYMLINK_MODE = "120000"
GITLINK_MODE = "160000"
REGULAR_MODES = frozenset({"100644", "100755"})
LFS_POINTER = b"version https://git-lfs.github.com/spec/v1"
# Blocks, "This is a macOS or Windows system file", at any depth.
SYSTEM_FILES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini", "__MACOSX"})
# Validation stops: a name Windows or macOS cannot hold. The page's examples are a colon, a trailing
# dot or space, a Windows device name such as `con.md` or `prn`, and two names that differ only by
# capitalization. The characters below are the whole set Windows refuses in a name, the colon among
# them, and a device name is reserved whatever extension follows it.
INVALID_CHARACTERS = frozenset('<>:"\\|?*') | frozenset(map(chr, range(32)))
DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"{port}{n}" for port in ("COM", "LPT") for n in range(1, 10)}
)
# Validation stops: in any `.gitattributes`, the two export attributes, and the attributes that
# rewrite a file's content on its way out of git. The page names `filter`, Git LFS's included, and
# "other content-rewriting attributes"; `ident` and `working-tree-encoding` are the two git defines.
# `text` and `eol` are left out: they convert line endings, which the page does not name, and
# `* text=auto` is the commonest line a `.gitattributes` holds.
EXPORT_ATTRIBUTES = ("export-ignore", "export-subst")
REWRITING_ATTRIBUTES = ("filter", "ident", "working-tree-encoding")
REFUSED_ATTRIBUTES = EXPORT_ATTRIBUTES + REWRITING_ATTRIBUTES
# What proves the walk read this repository: the manifest that makes the folder a plugin at all.
PLUGIN_MANIFEST = ".claude-plugin/plugin.json"

# `(path, size in bytes, git mode)`, the path relative to the root with `/` between components.
Entry = tuple[str, int, str]


def payload_findings(entries: Iterable[Entry], *, read: Callable[[str], bytes]) -> list[str]:
    """Every way `entries` falls outside the directory's rules, one finding per path and check.

    `read` returns a regular file's bytes: the binary and Git LFS checks read its start, and the
    `.gitattributes` check its lines. An attribute is matched on any line that carries it, a
    comment included: the directory's check is stated over the file's lines, and this reads them
    no more kindly.
    """
    listed = list(entries)
    findings = []
    if len(listed) > FILES_MAX:
        findings.append(f"{len(listed)} files, over the {FILES_MAX} the directory lists unheld")
    findings.extend(_name_findings([path for path, _, _ in listed]))
    for path, size, mode in listed:
        components = path.split("/")
        exempt = path.lower().endswith(EXEMPT_SUFFIXES)
        if size >= FILE_MAX_BYTES and not exempt:
            findings.append(f"{path}: {size} bytes, at or over {FILE_MAX_BYTES}")
        if mode == SYMLINK_MODE:
            findings.append(f"{path}: a tracked symlink")
        if mode == GITLINK_MODE:
            findings.append(f"{path}: a submodule")
        if SYSTEM_FILES.intersection(components):
            findings.append(f"{path}: a macOS or Windows system file")
        if mode not in REGULAR_MODES:
            continue
        content = read(path)
        if content.startswith(LFS_POINTER):
            findings.append(f"{path}: a Git LFS pointer")
        elif b"\0" in content[:BINARY_PROBE_BYTES] and not exempt:
            findings.append(f"{path}: a binary file that is not an image or a font")
        if components[-1] == ".gitattributes":
            findings.extend(
                f"{path}:{number}: {attribute}"
                for number, line in enumerate(content.decode("utf-8", "replace").splitlines(), 1)
                for attribute in _attributes(line)
                if attribute in REFUSED_ATTRIBUTES
            )
    return findings


def _attributes(line: str) -> list[str]:
    """The attribute names a `.gitattributes` line sets, unsets or values: every word after the
    first, which is the pattern, with a leading `-` or `!` and any `=value` taken off."""
    return [word.lstrip("-!").split("=", 1)[0] for word in line.split()[1:]]


def _name_findings(paths: list[str]) -> list[str]:
    """Each path holding a component Windows or macOS cannot name, and each set of spellings,
    of files and directories alike, that differ only by capitalization."""
    findings = []
    spellings: dict[str, set[str]] = {}
    for path in paths:
        components = path.split("/")
        for depth, component in enumerate(components, 1):
            spelt = "/".join(components[:depth])
            spellings.setdefault(_folded(spelt), set()).add(spelt)
            if not _nameable(component):
                findings.append(f"{path}: {component!r} is not a name Windows or macOS holds")
    findings.extend(
        f"{' and '.join(sorted(spelt))}: names that differ only by capitalization"
        for spelt in spellings.values()
        if len(spelt) > 1
    )
    return findings


def _folded(name: str) -> str:
    """The key two spellings of one file share on a case-insensitive file system."""
    return name.casefold()


def _nameable(component: str) -> bool:
    if INVALID_CHARACTERS.intersection(component):
        return False
    if component.endswith((".", " ")):
        return False
    return component.split(".", 1)[0].upper() not in DEVICE_NAMES


def tracked_payload(root: Path = ROOT) -> tuple[list[Entry], dict[str, bytes]]:
    """Every path in `root`'s `HEAD` tree and each regular file's bytes: what the directory reads.

    `git ls-tree -r -l -z HEAD` gives one row per path with its mode and its blob's size — a
    submodule as a gitlink row whose size is `-`, a symlink as the link and never its target — and
    `git cat-file --batch` the blobs, asked by object id so that no name has to survive a line.
    """
    entries: list[Entry] = []
    objects: dict[str, str] = {}
    for record in git(root, "ls-tree", "-r", "-l", "-z", "HEAD").split("\0"):
        if not record:
            continue
        # `<mode> <type> <object> <size, padded>\t<path>`: the path is everything after the tab.
        meta, path = record.split("\t", 1)
        mode, _kind, obj, size = meta.split()
        entries.append((path, 0 if size == "-" else int(size), mode))
        if mode in REGULAR_MODES:
            objects[path] = obj
    return entries, dict(zip(objects, _blobs(root, list(objects.values())), strict=True))


def _blobs(root: Path, objects: list[str]) -> list[bytes]:
    """The bytes of each object in `objects`, in order, from one `git cat-file --batch`."""
    asked = "".join(f"{obj}\n" for obj in objects).encode("ascii")
    out, at, blobs = git_bytes(root, "cat-file", "--batch", stdin=asked), 0, []
    for _ in objects:
        # `<object> <type> <size>\n<content>\n`, once per object asked.
        header_end = out.index(b"\n", at)
        size = int(out[at:header_end].split()[2])
        blobs.append(out[header_end + 1 : header_end + 1 + size])
        at = header_end + 1 + size + 1
    return blobs


def _text(_: str) -> bytes:
    """A reader for cases about entries alone: every file a line of text."""
    return b"text\n"


def test_a_file_at_the_limit_is_a_finding() -> None:
    # Mutation (declared): the size comparison `>=` becomes `>` (a file of exactly 256 KiB passes).
    assert payload_findings([("big.toml", FILE_MAX_BYTES, "100644")], read=_text) != []
    assert payload_findings([("ok.toml", FILE_MAX_BYTES - 1, "100644")], read=_text) == []


@pytest.mark.parametrize("path", ["logo.png", "LOGO.PNG", "diagram.svg", "fonts/body.woff2"])
def test_an_image_or_a_font_is_exempt_from_the_size_limit(path: str) -> None:
    # Mutation: `.png` dropped from `IMAGE_SUFFIXES` -> the logo is a finding and its cases redden.
    # The upper-case spelling holds the `lower()` beside it: without it `LOGO.PNG` is a finding.
    assert payload_findings([(path, FILE_MAX_BYTES * 4, "100644")], read=_text) == []


def test_an_ico_is_a_binary_the_directory_holds() -> None:
    # The page names `.ico` beside `.pdf` and `.zip` as a binary that is held, and this module
    # once exempted it as an image. Mutation (declared): `.ico` back in `IMAGE_SUFFIXES` -> the
    # icon passes and this reddens.
    icon = b"\0\0\1\0\1\0\x10\x10"
    assert payload_findings([("favicon.ico", len(icon), "100644")], read=lambda _: icon) == [
        "favicon.ico: a binary file that is not an image or a font"
    ]


def test_one_file_past_the_count_is_a_finding() -> None:
    # Mutation (declared): `>` becomes `>=` -> exactly `FILES_MAX` files is a finding, and the
    # second assertion reddens; `> FILES_MAX + 1` instead lets the first pass on nothing.
    entries = [(f"f{i}", 1, "100644") for i in range(FILES_MAX + 1)]
    assert any("files" in f for f in payload_findings(entries, read=_text))
    assert payload_findings(entries[:FILES_MAX], read=_text) == []


def test_a_symlink_is_a_finding() -> None:
    # Mutation (declared): the mode comparison becomes `!=` -> the symlink passes, and this
    # reddens; so does every other case here, each built of regular files.
    assert payload_findings([("link", 10, SYMLINK_MODE)], read=_text) != []
    assert payload_findings([("file", 10, "100644")], read=_text) == []


def test_a_submodule_is_a_finding() -> None:
    # A gitlink has no blob to read, so the content checks must pass over it rather than ask.
    # Mutation (declared): the gitlink comparison becomes `!=` -> the submodule passes, and this
    # reddens. Mutation: the `REGULAR_MODES` test dropped -> `read` is asked for the gitlink and
    # raises here.
    def unreadable(path: str) -> bytes:
        raise AssertionError(f"{path} has no blob")

    assert payload_findings([("vendor/lib", 0, GITLINK_MODE)], read=unreadable) == [
        "vendor/lib: a submodule"
    ]


@pytest.mark.parametrize(
    "path",
    [
        ".DS_Store",
        "docs/.DS_Store",
        "__MACOSX/a.txt",
        "a/__MACOSX/b",
        "Thumbs.db",
        "docs/img/Thumbs.db",
        "desktop.ini",
        "skills/desktop.ini",
    ],
)
def test_a_system_file_is_a_finding_at_any_depth(path: str) -> None:
    # Mutation (declared): `components` becomes `components[:1]` -> only a top-level system file is
    # a finding, and the nested cases redden. Mutation: `Thumbs.db` or `desktop.ini` dropped from
    # `SYSTEM_FILES` -> its two cases redden.
    assert payload_findings([(path, 10, "100644")], read=_text) == [
        f"{path}: a macOS or Windows system file"
    ]


def test_a_name_that_only_contains_a_system_files_name_is_not_a_finding() -> None:
    # The match is on whole components: a substring match would refuse a file merely named after
    # one. Mutation: `SYSTEM_FILES.intersection(components)` becomes
    # `any(name in path for name in SYSTEM_FILES)` -> this reddens.
    assert payload_findings([("docs/about.DS_Store.md", 10, "100644")], read=_text) == []


@pytest.mark.parametrize(
    "path",
    [
        "docs/a:b.md",
        "notes.",
        "a /b.md",
        "docs/what?.md",
        "tab\there.md",
        "con.md",
        "PRN",
        "docs/aux.txt",
        "nul.tar.gz",
        "COM1",
        "lpt9.log",
    ],
)
def test_a_name_windows_or_macos_cannot_hold_is_a_finding(path: str) -> None:
    # Mutations (declared): the device-name test answers yes -> the six device cases redden; the
    # trailing dot or space test dropped -> `notes.` and `a /b.md` redden. Mutation: the colon
    # dropped from `INVALID_CHARACTERS` -> `docs/a:b.md` reddens.
    found = payload_findings([(path, 10, "100644")], read=_text)
    assert len(found) == 1 and "is not a name Windows or macOS holds" in found[0], found


@pytest.mark.parametrize("path", ["console.md", "COM10", "auxiliary/x.md", "nullable.py", "a.b"])
def test_a_name_that_only_resembles_a_device_name_is_not_a_finding(path: str) -> None:
    # A device name is the whole name before its first dot. Mutation: the comparison becomes a
    # `startswith` over `DEVICE_NAMES` -> the first four redden.
    assert payload_findings([(path, 10, "100644")], read=_text) == []


@pytest.mark.parametrize(
    ("paths", "spelt"),
    [
        pytest.param(["README.md", "readme.md"], "README.md and readme.md", id="files"),
        pytest.param(["Docs/a.md", "docs/b.md"], "Docs and docs", id="directories"),
    ],
)
def test_names_that_differ_only_by_capitalization_are_a_finding(
    paths: list[str], spelt: str
) -> None:
    # On the default macOS and Windows file systems the two are one file, or one directory: the
    # second case is two files whose directories collide. Mutation (declared): `_folded` answers
    # its name unchanged -> no two spellings meet and both cases redden.
    found = payload_findings([(path, 10, "100644") for path in paths], read=_text)
    assert found == [f"{spelt}: names that differ only by capitalization"]


@pytest.mark.parametrize(
    ("path", "content"),
    [
        pytest.param("manual.pdf", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n\0", id="pdf"),
        pytest.param("scripts/tool", b"\x7fELF\x02\x01\x01\0", id="executable"),
        pytest.param("bundle.zip", b"PK\x03\x04\x14\0", id="zip"),
    ],
)
def test_a_binary_that_is_not_an_image_or_a_font_is_a_finding(path: str, content: bytes) -> None:
    # Mutation (declared): the NUL test dropped -> every case reddens.
    assert payload_findings([(path, len(content), "100644")], read=lambda _: content) == [
        f"{path}: a binary file that is not an image or a font"
    ]


def test_binary_is_judged_where_git_judges_it() -> None:
    # An image is a binary the page admits; a NUL past git's 8000-byte window is text to git.
    # Mutation: the window `[:BINARY_PROBE_BYTES]` dropped -> the late NUL is a finding and this
    # reddens. Mutation: `and not exempt` dropped from the binary test -> the PNG reddens it.
    png = b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR"
    late = b"x" * BINARY_PROBE_BYTES + b"\0"
    assert payload_findings([("logo.png", len(png), "100644")], read=lambda _: png) == []
    assert payload_findings([("notes.txt", len(late), "100644")], read=lambda _: late) == []


def test_a_git_lfs_pointer_is_a_finding() -> None:
    # A pointer is text, so the binary test passes it, and what the directory would load in the
    # file's place is three lines of metadata. Mutation (declared): the pointer test dropped ->
    # this reddens.
    pointer = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:4d7a214614ab2935c943f9e0ff69d22eadbb8f32b1258daaa5e2ca24d17e2393\n"
        b"size 12345\n"
    )
    found = payload_findings([("assets/demo.mp4", len(pointer), "100644")], read=lambda _: pointer)
    assert found == ["assets/demo.mp4: a Git LFS pointer"]


# Spelled out rather than parametrised over `EXPORT_ATTRIBUTES`, which would drop a case with the
# attribute it lost.
@pytest.mark.parametrize("attribute", ["export-ignore", "export-subst"])
def test_a_gitattributes_line_carrying_an_export_attribute_is_a_finding(attribute: str) -> None:
    # Mutation (declared): the `.gitattributes` test compares against `.gitattribute` -> no file
    # is read, and both cases redden. Mutation: either attribute dropped from
    # `EXPORT_ATTRIBUTES` -> its case reddens.
    text = f"*.md text\ndocs/** {attribute}\n".encode()
    found = payload_findings([("sub/.gitattributes", len(text), "100644")], read=lambda _: text)
    assert found == [f"sub/.gitattributes:2: {attribute}"]


@pytest.mark.parametrize(
    ("line", "attribute"),
    [
        pytest.param("*.bin filter=lfs diff=lfs merge=lfs -text", "filter", id="lfs"),
        pytest.param("*.c -filter", "filter", id="filter-unset"),
        pytest.param("*.c ident", "ident", id="ident"),
        pytest.param("*.ps1 working-tree-encoding=UTF-16", "working-tree-encoding", id="encoding"),
    ],
)
def test_a_gitattributes_line_rewriting_content_is_a_finding(line: str, attribute: str) -> None:
    # Mutation (declared): `filter` dropped from `REWRITING_ATTRIBUTES` -> the two `filter` cases
    # redden; `ident` or `working-tree-encoding` dropped -> its case reddens. The `-filter` case
    # holds the `lstrip("-!")` in `_attributes`: without it an unset reads as another name.
    text = f"{line}\n".encode()
    found = payload_findings([(".gitattributes", len(text), "100644")], read=lambda _: text)
    assert found == [f".gitattributes:1: {attribute}"]


@pytest.mark.parametrize("line", ["*.md text eol=lf", "filter text", "*.txt diff=filtered"])
def test_a_gitattributes_line_carrying_no_refused_attribute_is_not_a_finding(line: str) -> None:
    # The file itself is allowed; only the attributes the page names are not. The second case is a
    # pattern, the files named `filter`, and the third a value that only contains an attribute.
    # Mutation: `_attributes` reads every word, the pattern included -> the second case reddens.
    # Mutation: a finding for every `.gitattributes` whatever its lines -> every case reddens.
    text = f"{line}\n".encode()
    assert payload_findings([(".gitattributes", len(text), "100644")], read=lambda _: text) == []


def test_the_plugin_folder_is_the_repository_root() -> None:
    # If the plugin moves into a subfolder, the payload is that folder and this module's walk
    # is wrong; it must change with the move rather than go on passing over the wrong tree.
    # Mutation: the marketplace's `source` becomes `./plugin` -> this reddens.
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text("utf-8"))
    assert [p["source"] for p in market["plugins"]] == ["./"]


@needs_git
def test_the_walk_reads_the_committed_tree_and_not_the_disk(tmp_path: Path) -> None:
    # The directory scans a commit, so a size measured on disk, a file deleted from the working
    # tree, a file only staged, or a symlink followed to its target is a different payload from the
    # one it reads. The gitlink is planted in the index by hand: the listing must name it with no
    # blob to ask for. Mutation: the size read from `(root / path).lstat()` instead of the listing
    # -> the edited file's row reddens. The staged file holds the listing to `HEAD` rather than the
    # index; the one-line swap to `ls-files -s` reddens this too, but by breaking the row parse,
    # since an index row has three fields before its tab, so it proves the parse and not the choice.
    root = tmp_path / "plugin"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "a.md").write_text("one\n", encoding="utf-8")
    (root / "gone.md").write_text("two\n", encoding="utf-8")
    os.symlink("a.md", root / "link")
    git(root, "add", "-A")
    commit = git(root, "commit-tree", git(root, "write-tree").strip(), "-m", "x").strip()
    git(root, "update-index", "--add", "--cacheinfo", f"{GITLINK_MODE},{commit},vendor")
    git(root, "commit", "-q", "-m", "payload")
    (root / "a.md").write_text("one, and an edit nobody committed\n", encoding="utf-8")
    (root / "gone.md").unlink()
    (root / "staged.md").write_text("three\n", encoding="utf-8")
    git(root, "add", "staged.md")

    entries, blobs = tracked_payload(root)

    assert sorted(entries) == [
        ("a.md", 4, "100644"),
        ("gone.md", 4, "100644"),
        ("link", 4, SYMLINK_MODE),
        ("vendor", 0, GITLINK_MODE),
    ]
    assert blobs == {"a.md": b"one\n", "gone.md": b"two\n"}


# Both marks: `needs_git` for a machine with no `git`, and the second for an unpacked sdist, which
# has `git` but is not a checkout, so there is no tree to list. Neither is what the directory
# scans, so the skip costs nothing there.
@needs_git
@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="no git checkout to ask")
def test_the_tree_is_inside_the_directory_limits() -> None:
    # No mutation of the code: the subject is the tree. Watched red by lowering `FILES_MAX`
    # below the tracked count, which is what the tree outgrowing it looks like from here.
    entries, blobs = tracked_payload()
    # A walk-based assertion states its walk is non-empty, and this one that it walked this plugin.
    assert PLUGIN_MANIFEST in {path for path, _, _ in entries}, len(entries)
    assert payload_findings(entries, read=blobs.__getitem__) == []
