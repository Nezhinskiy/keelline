"""Where the notes are, and the four ways that answer can be a lie (§9.1).

A store is a per-project value with no machine-level default, because the wrong answer is not
"no memory" but *another project's* memory reaching this session. Four things are therefore
checked, and each closes a hole the other three leave open:

1. **The shape.** In overlay mode `paths.memory` is a real directory holding one link per
   group (§6.3). It is not one link: `developer` points into the overlay's `common/memory`,
   which is shared across projects and cannot live under `projects/<name>/`. A single link at
   `paths.memory` would lose the cross-project half of the store outright.
2. **Containment inside the store.** A group name is repository-controlled — `memory.groups`
   is an ordinary `keelline.toml` list — so `groups = ["../secret"]` must not become a read,
   and certainly not a write, outside the store. `config/paths.py` says in as many words that
   this field reaches no guard of its own and that the lane consuming it owns the check.
3. **The link's target.** A link is honoured only when it lands inside *this project's* share
   of the recorded overlay: `common/memory`, or `projects/<the bound name>/memory`. Testing
   containment in the overlay root alone lets an honestly-named, honestly-bound project point
   one directory sideways at another client's notes.
4. **The binding.** The overlay's `projects/<name>/project.toml` must record this
   repository's own `origin`. `git` runs with a scrubbed environment, because an inherited
   `GIT_DIR` would otherwise answer for a different repository altogether.

The environment selects nothing. A committed `.claude/settings.json` may carry an `env` block
that applies with no trust prompt in a non-interactive session, so neither the store nor the
machine file is ever named by a variable this process reads.
"""

from __future__ import annotations

import os
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from keelline.config.machine import machine_config_path
from keelline.config.paths import PathEscape, contained
from keelline.config.schema import Config

LOCAL_STORE = Path(".keelline") / "local" / "memory"
PROJECT_RECORD = "project.toml"
COMMON = Path("common") / "memory"
_GIT_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT")


@dataclass(frozen=True)
class Store:
    path: Path
    mode: str
    root: Path
    groups: dict[str, Path] = field(default_factory=dict)
    unavailable: dict[str, str] = field(default_factory=dict)

    def group_dir(self, group: str) -> Path | None:
        return self.groups.get(group)


def _git(root: Path, *args: str) -> str | None:
    env = {key: os.environ[key] for key in _GIT_ENV_KEEP if key in os.environ}
    try:
        done = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=5, env=env
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else None


def main_checkout(root: Path) -> Path:
    """The checkout that owns the store, for a session running inside a worktree.

    The result must be an ancestor of nothing and a sibling of anything — but it must be a
    real git answer, not one an inherited `GIT_DIR` produced, which is why `_git` scrubs.
    """
    common = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(common).parent if common else root


def overlay_root(machine: Path | None) -> Path | None:
    path = machine_config_path(interactive=False) if machine is None else machine
    if not path.is_file():
        return None
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    section = raw.get("overlay")
    if not isinstance(section, dict):
        return None
    value = section.get("root")
    return Path(str(value)).expanduser() if isinstance(value, str) and value else None


def _bound(overlay: Path, project: str, root: Path) -> bool:
    record = overlay / "projects" / project / PROJECT_RECORD
    if not record.is_file():
        return False
    try:
        raw = tomllib.loads(record.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    recorded = raw.get("remote")
    if not isinstance(recorded, str) or not recorded:
        return False
    return _git(root, "remote", "get-url", "origin") == recorded


def _inside(candidate: Path, parent: Path) -> bool:
    resolved = candidate.resolve()
    base = parent.resolve()
    return resolved == base or base in resolved.parents


def permitted_roots(overlay: Path, project: str) -> tuple[Path, Path]:
    """This project's whole share of the overlay: the common notes and its own (§6.2)."""
    return overlay / COMMON, overlay / "projects" / project / "memory"


def _declared(root: Path, config: Config) -> Path | None:
    try:
        return contained(root, config.paths.memory, allow_final_symlink=True)
    except PathEscape:
        return None


def _group_targets(
    base: Path, config: Config, overlay: Path | None
) -> tuple[dict[str, Path], dict[str, str]]:
    groups: dict[str, Path] = {}
    unavailable: dict[str, str] = {}
    for group in config.memory.groups:
        try:
            target = contained(base, group, allow_final_symlink=True)
        except PathEscape as exc:
            unavailable[group] = str(exc)
            continue
        if not target.exists():
            unavailable[group] = f"{group} is not in the store"
            continue
        if target.is_symlink():
            if overlay is None:
                unavailable[group] = f"{group} is a link and no overlay is recorded"
                continue
            allowed = permitted_roots(overlay, config.project.name)
            if not any(_inside(target, permitted) for permitted in allowed):
                unavailable[group] = (
                    f"{group} links outside this project's share of the overlay "
                    f"({', '.join(str(p) for p in allowed)})"
                )
                continue
        groups[group] = target
    return groups, unavailable


def _resolve_at(
    root: Path, config: Config, override: str | None, machine: Path | None
) -> tuple[Store | None, str | None]:
    mode = config.memory.mode
    overlay = overlay_root(machine)
    if override is not None:
        base = Path(override).expanduser()
    elif mode == "local-only":
        base = root / LOCAL_STORE
    else:
        declared = _declared(root, config)
        if declared is None:
            return None, f"paths.memory ({config.paths.memory!r}) does not stay inside the project"
        base = declared
        if mode == "in-repo" and declared.is_symlink():
            return None, f"{config.paths.memory} is a symlink; in-repo memory is a real directory"
    if mode == "overlay":
        if overlay is None:
            return (
                None,
                "no overlay root is recorded in the machine configuration; run `keelline setup`",
            )
        if not _bound(overlay, config.project.name, root):
            return None, (
                f"the overlay does not record this repository's origin remote for project "
                f"{config.project.name!r}; run `keelline attach`"
            )
    if not base.is_dir():
        return None, f"{base} does not exist; run `keelline attach`"
    groups, unavailable = _group_targets(base, config, overlay if mode == "overlay" else None)
    if not groups:
        reason = "; ".join(f"{k}: {v}" for k, v in unavailable.items()) or "the store has no groups"
        return None, reason
    return Store(base, mode, root, groups, unavailable), None


def resolve(
    root: Path,
    config: Config,
    *,
    override: str | None = None,
    machine: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Store | None:
    # `env` is accepted and never read: §9.1 forbids selecting a store through the
    # environment, and a parameter that exists and is ignored is a claim a test can pin.
    del env
    store, _ = _resolve_at(root, config, override, machine)
    if store is not None:
        return store
    parent = main_checkout(root)
    if parent.resolve() == root.resolve() or not _inside(root, parent):
        # A worktree resolves through the checkout that contains it, never through whatever a
        # redirected `GIT_DIR` named: the fallback only runs when the answer really is a parent.
        return None
    store, _ = _resolve_at(parent, config, override, machine)
    return store


def refusal_reason(
    root: Path,
    config: Config,
    *,
    override: str | None = None,
    machine: Path | None = None,
) -> str | None:
    store, reason = _resolve_at(root, config, override, machine)
    if store is not None:
        return None
    parent = main_checkout(root)
    if parent.resolve() != root.resolve() and _inside(root, parent):
        upstream, upstream_reason = _resolve_at(parent, config, override, machine)
        return None if upstream is not None else upstream_reason
    return reason


def inside_project(store: Store) -> bool:
    """Whether any note actually lives in the repository — the predicate §9.4 turns on.

    Not `memory.mode`, which the clone chooses, and not the store directory, which in overlay
    mode is a real directory of links inside the project. What decides whether a note is the
    machine owner's or the repository's is where the note itself sits: `local-only` puts it
    under `.keelline/local/`, which a `.gitignore` keeps out of a clone the owner made and
    does not keep out of a clone the attacker authored.
    """
    return any(_inside(target, store.root) for target in store.groups.values())
