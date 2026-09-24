"""A profile's checks against a repository, reading only files and the git index.

| Kind | A finding when | `located` names |
|---|---|---|
| `present` | no locator resolves | every locator's `at` |
| `absent` | some locator resolves | each `at` that resolved |
| `tracked` | a located file is neither tracked nor ignored | each `at` that found one |

A locator resolves when:
- its `at` names at least one regular file at or under the root, reached through no symlink
  (`contained`);
- then, when it names a `toml` key or an `ini` section or key, that key is present in a file
  that parses;
- then, when it carries a `match`, the value's text matches it.

**A value's text** is:
- a string, as written;
- a boolean, as TOML spells it (`true`);
- a number, as written;
- a list, as its items joined by one space.

That is the whole coercion, and it is what the profile's patterns are written against.

**The repository's bytes stay inside this module.** Parsing may fail, and then the locator
resolves to nothing. No exception text and no value reaches an `Outcome`. `located` carries
the profile's own `at` strings, which are the plugin's, never a file name a glob found.
"""

from __future__ import annotations

import configparser
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from keelline.config.paths import PathEscape, contained
from keelline.gitenv import git_run
from keelline.profiles.model import Check, CheckKind, Locator, Profile

_GLOB = frozenset("*?[")
_TEXT_CAP = 1024 * 1024  # a profile reads configuration files, never anything this large


@dataclass(frozen=True)
class Outcome:
    check: Check
    located: tuple[str, ...]


def _files(root: Path, at: str) -> list[str]:
    """Root-relative regular files `at` names, each reached through no symlink."""
    candidates = (
        [p.relative_to(root).as_posix() for p in sorted(root.glob(at))] if _GLOB & set(at) else [at]
    )
    found: list[str] = []
    for relative in candidates:
        try:
            path = contained(root, relative)
        except PathEscape:
            continue
        if path.is_file():
            found.append(relative)
    return found


def _read(root: Path, relative: str) -> str | None:
    try:
        path = contained(root, relative)
        if path.stat().st_size > _TEXT_CAP:
            return None
        return path.read_text(encoding="utf-8")
    except (PathEscape, OSError, UnicodeDecodeError):
        return None


def _text(value: Any) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    if isinstance(value, list):
        parts = [_text(item) for item in value]
        return " ".join(part for part in parts if part is not None)
    if isinstance(value, dict):
        return ""  # a table is present; it has no text of its own
    return None


def _toml_value(text: str, dotted: str) -> str | None:
    try:
        node: Any = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return _text(node)


def _ini_value(text: str, address: tuple[str, ...]) -> str | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(text)
    except configparser.Error:
        return None
    section, key = address[0], address[1] if len(address) == 2 else None
    if not parser.has_section(section):
        return None
    if key is None:
        return ""
    return parser.get(section, key) if parser.has_option(section, key) else None


def _resolves(root: Path, locator: Locator) -> bool:
    for relative in _files(root, locator.at):
        value: str | None = ""
        if locator.toml is not None or locator.ini is not None:
            text = _read(root, relative)
            if text is None:
                continue
            value = (
                _toml_value(text, locator.toml)
                if locator.toml is not None
                else _ini_value(text, locator.ini or ())
            )
        if value is None:
            continue
        if locator.match is not None and not locator.match.search(value):
            continue
        return True
    return False


def _untracked(root: Path, relative: str) -> bool:
    """Untracked and not ignored: `--others` lists what the index lacks, and `--exclude-standard`
    drops what `.gitignore`, `info/exclude` and `core.excludesFile` ignore. A lockfile a library
    ignores on purpose is a decision, not a file somebody forgot to commit.

    Outside a work tree `git ls-files` exits non-zero and writes nothing to stdout, so a
    directory that is no repository answers "not untracked" and has nothing to report; no
    second probe asks it first. `code == 0` says so explicitly rather than trusting the empty
    output alone.
    """
    code, out = git_run(root, "ls-files", "--others", "--exclude-standard", "--", relative)
    return code == 0 and bool(out.strip())


def detects(profile: Profile, root: Path) -> bool:
    return any(_files(root, at) for at in profile.detect)


def _names(locators: list[Locator]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(locator.at for locator in locators))


def evaluate(profile: Profile, root: Path) -> list[Outcome]:
    outcomes: list[Outcome] = []
    for check in profile.checks:
        locators = list(check.locators)
        if check.kind is CheckKind.PRESENT:
            hits = [] if any(_resolves(root, loc) for loc in locators) else locators
        elif check.kind is CheckKind.ABSENT:
            hits = [loc for loc in locators if _resolves(root, loc)]
        else:
            hits = [
                loc for loc in locators if any(_untracked(root, f) for f in _files(root, loc.at))
            ]
        if hits:
            outcomes.append(Outcome(check, _names(hits)))
    return outcomes
