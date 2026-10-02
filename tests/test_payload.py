"""The plugin folder held to the file limits the Claude plugin directory checks at submission.

The payload is every file git tracks, because the plugin folder is the repository root: the
marketplace's one plugin has `source` `./`, and `test_the_plugin_folder_is_the_repository_root`
reddens the day it moves, so that this walk changes with the move instead of going on passing over
the wrong tree.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

from tests.gitfixture import git, needs_git

ROOT = Path(__file__).resolve().parents[1]

# The directory's limits, as its pre-submission checklist states them
# (https://claude.com/docs/plugins/pre-submission-checklist, read 2026-10-02; the page carries no
# date). The two numbers are soft limits: a file that is not an image or a font at
# `FILE_MAX_BYTES` or more, or more than `FILES_MAX` files, puts the listing on hold for a reviewer
# rather than blocking it. A symlink, an archive tool's leftover and an export attribute below are
# hard blocks. The plugin folder they apply to is the repository root, because the marketplace's
# `source` is `./`.
FILE_MAX_BYTES = 256 * 1024
FILES_MAX = 512
EXEMPT_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
)
SYMLINK_MODE = "120000"
LEFTOVERS = frozenset({".DS_Store", "__MACOSX"})
EXPORT_ATTRIBUTES = ("export-ignore", "export-subst")

# `(path, size in bytes, git mode)`, the path relative to the root with `/` between components.
Entry = tuple[str, int, str]


def _tracked_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def payload_findings(
    entries: Iterable[Entry], *, read: Callable[[str], str] = _tracked_text
) -> list[str]:
    """Every way `entries` falls outside the directory's limits, one finding per path and check.

    `read` returns a `.gitattributes` file's text, the one check that needs a file's lines rather
    than its entry. An attribute is matched on any line that carries it, a comment included:
    the directory's check is stated over the file's lines, and this reads them no more kindly.
    """
    listed = list(entries)
    findings = []
    if len(listed) > FILES_MAX:
        findings.append(f"{len(listed)} files, over the {FILES_MAX} the directory lists unheld")
    for path, size, mode in listed:
        components = path.split("/")
        if size >= FILE_MAX_BYTES and not path.lower().endswith(EXEMPT_SUFFIXES):
            findings.append(f"{path}: {size} bytes, at or over {FILE_MAX_BYTES}")
        if mode == SYMLINK_MODE:
            findings.append(f"{path}: a tracked symlink")
        if LEFTOVERS.intersection(components):
            findings.append(f"{path}: an archive tool's leftover")
        if components[-1] == ".gitattributes":
            findings.extend(
                f"{path}:{number}: {attribute}"
                for number, line in enumerate(read(path).splitlines(), start=1)
                for attribute in EXPORT_ATTRIBUTES
                if attribute in line
            )
    return findings


def tracked_entries() -> list[Entry]:
    """Every index entry under `ROOT`, with its mode from git and its size from the disk.

    `lstat` and not `stat`: a tracked symlink is a finding in itself, and following it would read
    the size of whatever it points at, or raise on one that dangles.
    """
    entries = []
    for record in git(ROOT, "ls-files", "-s", "-z").split("\0"):
        if not record:
            continue
        # `<mode> <object> <stage>\t<path>`: the path is everything after the tab.
        meta, path = record.split("\t", 1)
        entries.append((path, (ROOT / path).lstat().st_size, meta.split(" ", 1)[0]))
    return entries


def test_a_file_at_the_limit_is_a_finding() -> None:
    # Mutation (declared): the size comparison `>=` becomes `>` (a file of exactly 256 KiB passes).
    assert payload_findings([("big.toml", FILE_MAX_BYTES, "100644")]) != []
    assert payload_findings([("ok.toml", FILE_MAX_BYTES - 1, "100644")]) == []


def test_an_image_is_exempt_from_the_size_limit() -> None:
    # Mutation: `.png` dropped from `EXEMPT_SUFFIXES` -> the logo is a finding and this reddens.
    # The upper-case spelling holds the `lower()` beside it: without it `LOGO.PNG` is a finding.
    assert payload_findings([("logo.png", FILE_MAX_BYTES * 4, "100644")]) == []
    assert payload_findings([("LOGO.PNG", FILE_MAX_BYTES * 4, "100644")]) == []


def test_one_file_past_the_count_is_a_finding() -> None:
    # Mutation (declared): `>` becomes `>=` -> exactly `FILES_MAX` files is a finding, and the
    # second assertion reddens; `> FILES_MAX + 1` instead lets the first pass on nothing.
    entries = [(f"f{i}", 1, "100644") for i in range(FILES_MAX + 1)]
    assert any("files" in f for f in payload_findings(entries))
    assert payload_findings(entries[:FILES_MAX]) == []


def test_a_symlink_is_a_finding() -> None:
    # Mutation (declared): the mode comparison becomes `!=` -> the symlink passes, and this
    # reddens; so does every other case here, each built of regular files.
    assert payload_findings([("link", 10, "120000")]) != []
    assert payload_findings([("file", 10, "100644")]) == []


@pytest.mark.parametrize("path", [".DS_Store", "docs/.DS_Store", "__MACOSX/a.txt", "a/__MACOSX/b"])
def test_an_archive_tools_leftover_is_a_finding_at_any_depth(path: str) -> None:
    # Mutation (declared): `components` becomes `components[:1]` -> only a top-level leftover is
    # a finding, and the nested cases redden.
    assert payload_findings([(path, 10, "100644")]) != []


def test_a_name_that_only_contains_a_leftovers_name_is_not_a_finding() -> None:
    # The match is on whole components: a substring match would refuse a file merely named after
    # one. Mutation: `LEFTOVERS.intersection(components)` becomes
    # `any(name in path for name in LEFTOVERS)` -> this reddens.
    assert payload_findings([("docs/about.DS_Store.md", 10, "100644")]) == []


# Spelled out rather than parametrised over `EXPORT_ATTRIBUTES`, which would drop a case with the
# attribute it lost.
@pytest.mark.parametrize("attribute", ["export-ignore", "export-subst"])
def test_a_gitattributes_line_carrying_an_export_attribute_is_a_finding(attribute: str) -> None:
    # Mutation (declared): the `.gitattributes` test compares against `.gitattribute` -> no file
    # is read, and both cases redden. Mutation: either attribute dropped from
    # `EXPORT_ATTRIBUTES` -> its case reddens.
    text = f"*.md text\ndocs/** {attribute}\n"
    found = payload_findings([("sub/.gitattributes", len(text), "100644")], read=lambda _: text)
    assert found == [f"sub/.gitattributes:2: {attribute}"]


def test_a_gitattributes_without_an_export_attribute_is_not_a_finding() -> None:
    # The file itself is allowed; only the two attributes are blocks. Mutation: a finding for every
    # `.gitattributes` whatever its lines -> this reddens.
    text = "*.md text eol=lf\n"
    assert payload_findings([(".gitattributes", len(text), "100644")], read=lambda _: text) == []


def test_the_plugin_folder_is_the_repository_root() -> None:
    # If the plugin moves into a subfolder, the payload is that folder and this module's walk
    # is wrong; it must change with the move rather than go on passing over the wrong tree.
    # Mutation: the marketplace's `source` becomes `./plugin` -> this reddens.
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text("utf-8"))
    assert [p["source"] for p in market["plugins"]] == ["./"]


# Both marks: `needs_git` for a machine with no `git`, and the second for an unpacked sdist, which
# has `git` but is not a checkout, so there is no index to list. Neither is what the directory
# scans, so the skip costs nothing there.
@needs_git
@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="no git checkout to ask")
def test_the_tree_is_inside_the_directory_limits() -> None:
    # No mutation of the code: the subject is the tree. Watched red by lowering `FILES_MAX`
    # below the tracked count, which is what the tree outgrowing it looks like from here.
    entries = tracked_entries()
    # A walk-based assertion states its walk is non-empty: an index read as nothing passes.
    assert len(entries) > FILES_MAX // 2, len(entries)
    assert payload_findings(entries) == []
