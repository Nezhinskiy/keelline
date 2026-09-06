from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

SOURCES = (
    "pyproject.toml",
    "src/keelline/__init__.py",
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    "CHANGELOG.md",
)
MARKETPLACE = ".claude-plugin/marketplace.json"
START = "<!-- towncrier release notes start -->"
_INIT = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.MULTILINE)
_HEADING = re.compile(r"^## (\S+)", re.MULTILINE)


def _read(root: Path, name: str) -> str | None:
    path = root / name
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if name == "pyproject.toml":
        version = tomllib.loads(text).get("project", {}).get("version")
        return str(version) if version is not None else None
    if name.endswith("__init__.py"):
        match = _INIT.search(text)
        return match.group(1) if match else None
    if name.endswith(".json"):
        version = json.loads(text).get("version")
        return str(version) if version is not None else None
    released = text.split(START, 1)[1] if START in text else text
    match = _HEADING.search(released)
    return match.group(1) if match else None


def collect(root: Path) -> dict[str, str | None]:
    return {name: _read(root, name) for name in SOURCES}


def pending_fragments(root: Path) -> bool:
    directory = root / "changelog.d"
    return directory.is_dir() and any(p.name != ".gitkeep" for p in directory.iterdir())


def check(root: Path) -> list[str]:
    found = collect(root)
    canonical = found["pyproject.toml"]
    if canonical is None:
        return ["pyproject.toml has no [project].version"]
    problems: list[str] = []
    for name, value in found.items():
        if name == "CHANGELOG.md" and pending_fragments(root):
            continue
        if value != canonical:
            problems.append(f"{name} says {value!r}; pyproject.toml says {canonical!r}")
    marketplace = root / MARKETPLACE
    if marketplace.is_file():
        entries = json.loads(marketplace.read_text(encoding="utf-8")).get("plugins", [])
        for entry in entries:
            if "version" in entry:
                problems.append(
                    f"{MARKETPLACE} entry {entry.get('name')!r} carries a version; "
                    "plugin.json is the only source (D12)"
                )
    return problems
