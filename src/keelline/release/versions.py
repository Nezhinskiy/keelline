"""One version string everywhere, and one honest answer about what is still pending."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from keelline.errors import Failure
from keelline.release.hashes import HASHED_FILES, RECORD, drift

PYPROJECT = "pyproject.toml"
LOCKFILE = "uv.lock"
PACKAGE = "keelline"
SOURCES = (
    PYPROJECT,
    LOCKFILE,
    "src/keelline/__init__.py",
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    "CHANGELOG.md",
)
MARKETPLACE = ".claude-plugin/marketplace.json"
START = "<!-- towncrier release notes start -->"
_INIT = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.MULTILINE)
_HEADING = re.compile(r"^## (\S+)", re.MULTILINE)


class MalformedSource(Failure):
    """A version source that exists but cannot be parsed; the message names which one."""


def _parse(name: str, text: str) -> str | None:
    if name == PYPROJECT:
        version = tomllib.loads(text).get("project", {}).get("version")
        return str(version) if version is not None else None
    if name == LOCKFILE:
        # `uv sync --locked` fails the install step on a stale lockfile with a
        # dependency-shaped message, before this gate — built to catch exactly this — can speak.
        packages = tomllib.loads(text).get("package", [])
        # Valid TOML of the wrong shape decodes cleanly, so `_read`'s decoder catches never see
        # it: iterating a string yields characters and `entry.get` raises AttributeError, which
        # reaches the caller as an unlabelled internal error naming no file. The lockfile owes
        # the same named failure every other malformed source already gets.
        if not isinstance(packages, list) or not all(isinstance(e, dict) for e in packages):
            raise MalformedSource(f"{name} is valid TOML but its package is not a list of tables")
        for entry in packages:
            if entry.get("name") == PACKAGE:
                version = entry.get("version")
                return str(version) if version is not None else None
        return None
    if name.endswith("__init__.py"):
        match = _INIT.search(text)
        return match.group(1) if match else None
    if name.endswith(".json"):
        version = json.loads(text).get("version")
        return str(version) if version is not None else None
    released = text.split(START, 1)[1] if START in text else text
    match = _HEADING.search(released)
    return match.group(1) if match else None


def _read(root: Path, name: str) -> str | None:
    path = root / name
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    try:
        return _parse(name, text)
    except tomllib.TOMLDecodeError as exc:
        raise MalformedSource(f"{name} is not valid TOML: {exc}") from None
    except json.JSONDecodeError as exc:
        raise MalformedSource(f"{name} is not valid JSON: {exc}") from None


def collect(root: Path) -> dict[str, str | None]:
    return {name: _read(root, name) for name in SOURCES}


def fragment_types(root: Path) -> frozenset[str]:
    """The types `[[tool.towncrier.type]]` declares, read rather than hardcoded here.

    A predicate that spelled the types out would drift from the configuration towncrier
    itself reads, and the drift would show up as a release gate that is wrong in silence.
    """
    tool = _pyproject(root).get("tool", {})
    towncrier = tool.get("towncrier", {}) if isinstance(tool, dict) else {}
    declared = towncrier.get("type", []) if isinstance(towncrier, dict) else []
    return frozenset(
        str(entry["directory"])
        for entry in declared
        if isinstance(entry, dict) and "directory" in entry
    )


def _pyproject(root: Path) -> dict[str, Any]:
    path = root / PYPROJECT
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise MalformedSource(f"{PYPROJECT} is not valid TOML: {exc}") from None


def _is_fragment(name: str, types: frozenset[str]) -> bool:
    """towncrier's own shape: `<something>.<type>.md`."""
    stem, _, extension = name.rpartition(".")
    if extension != "md" or not stem:
        return False
    prefix, _, kind = stem.rpartition(".")
    return bool(prefix) and kind in types


def pending_fragments(root: Path) -> bool:
    """Whether `changelog.d` holds a real towncrier fragment, letting CHANGELOG.md lag.

    Asking instead "any entry not literally named .gitkeep" meant a stray `.DS_Store` — which
    Finder writes merely by opening the directory — silenced a genuine version drift and turned
    a red release gate green.
    """
    directory = root / "changelog.d"
    if not directory.is_dir():
        return False
    types = fragment_types(root)
    return any(_is_fragment(entry.name, types) for entry in directory.iterdir())


def tag_for(version: str) -> tuple[str, str]:
    """The two tags one release carries: the workflow's `vX.Y.Z` and the platform's own."""
    return f"v{version}", f"{PACKAGE}--v{version}"


def check(root: Path, *, tag: str | None = None) -> list[str]:
    # Four different conditions used to share one wrong message, so a user who typoed --root,
    # or ran the command in their own project (--root defaults to "."), was told their
    # pyproject.toml lacked a version key. A path that exists but is not a directory needs its
    # own line rather than the missing-path one: `--root ./pyproject.toml` was told the file
    # does not exist, and a gate that exists to stop asserting untrue things about the user's
    # tree must not assert one itself.
    if not root.exists():
        return [f"{root} does not exist; --root must name a repository root"]
    if not root.is_dir():
        return [f"{root} is not a directory; --root must name a repository root"]
    if not (root / PYPROJECT).is_file():
        return [f"{root} has no {PYPROJECT}; --root must name a repository root"]
    found = collect(root)
    canonical = found[PYPROJECT]
    if canonical is None:
        return [f"{PYPROJECT} has no [project].version"]
    problems: list[str] = []
    if tag is not None:
        if tag not in tag_for(canonical):
            # **Say what was checked, do not re-derive a version from the tag.** This used to
            # be `tag.split("v", 1)[-1]` — a split on the first `v` anywhere in the string and
            # not a parse — so `--tag 1.2.3` reported `tag 1.2.3 names 1.2.3; pyproject.toml
            # says '1.2.3'`, two identical strings asserted to disagree, and `--tag dev-v1.2.3`
            # reported `names -v1.2.3`. The membership test above is exact and was always
            # right; only the sentence was invented. Both slips are the ones `RELEASING.md`
            # invites, because a human types this flag by hand right after a tool prints
            # `keelline--vX.Y.Z`. The existing cases passed by accident: every tag they
            # exercised began with `v` and carried no earlier one.
            workflow_tag, platform_tag = tag_for(canonical)
            problems.append(
                f"tag {tag} is neither {workflow_tag} nor {platform_tag}; "
                f"{PYPROJECT} says {canonical!r}"
            )
        if pending_fragments(root):
            count = sum(
                _is_fragment(e.name, fragment_types(root)) for e in (root / "changelog.d").iterdir()
            )
            problems.append(
                f"changelog.d still holds {count} fragment(s); run `keelline release notes "
                f"--version {canonical}` before tagging"
            )
    for name, value in found.items():
        if name == "CHANGELOG.md" and tag is None and pending_fragments(root):
            continue
        if value != canonical:
            problems.append(f"{name} says {value!r}; {PYPROJECT} says {canonical!r}")
    marketplace = root / MARKETPLACE
    if marketplace.is_file():
        entries = json.loads(marketplace.read_text(encoding="utf-8")).get("plugins", [])
        for entry in entries:
            if "version" in entry:
                problems.append(
                    f"{MARKETPLACE} entry {entry.get('name')!r} carries a version; "
                    "plugin.json is the only source of the version"
                )
    # The record of the shipped files is held current here and not only at a tag, so a
    # wrapper edited without `keelline release hashes` fails the gate the same commit.
    #
    # Asked of the recorded files themselves and not of a `hooks/` directory. `--root` defaults
    # to `.`, and a user who runs this in their own project must not be told a record they
    # never had is missing — and plenty of projects have a `hooks/` directory, which is what
    # the first spelling of this actually tested. Either the record is here, or every file it
    # would name is: the first keeps a tree whose wrapper was deleted honest, the second is how
    # a checkout with no record yet is told to write one.
    if (root / RECORD).is_file() or all((root / name).is_file() for name in HASHED_FILES):
        problems += drift(root)
    return problems
