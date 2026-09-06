"""Read keelline.toml, merge it under the machine config and the preset, validate it."""

from __future__ import annotations

import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any, TypeVar, cast

from keelline.config.machine import machine_config_path
from keelline.config.paths import validate_paths
from keelline.config.schema import (
    CI_MODES,
    MEMORY_MODES,
    PROJECT_NAME,
    STATES,
    Artifacts,
    Budgets,
    Ci,
    CommitMessages,
    Config,
    Keelline,
    Ledger,
    Memory,
    NativeCaps,
    Paths,
    Personal,
    Project,
)
from keelline.errors import Failure
from keelline.presets import load_preset

CONFIG_FILE = "keelline.toml"
SECTIONS = (
    "keelline",
    "project",
    "paths",
    "memory",
    "budgets",
    "ledger",
    "artifacts",
    "ci",
    "commit_messages",
)


T = TypeVar("T")


class ConfigError(Failure):
    """A keelline.toml that cannot be trusted as written."""


def _table(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] must be a table")
    return value


def _merged(raw: dict[str, Any], defaults: dict[str, Any], name: str) -> dict[str, Any]:
    return {**defaults.get(name, {}), **_table(raw, name)}


def _build(cls: type[T], name: str, values: dict[str, Any]) -> T:
    known = {f.name: f.type for f in fields(cast(Any, cls))}
    unknown = sorted(set(values) - set(known))
    if unknown:
        raise ConfigError(f"[{name}] has unknown key(s): {', '.join(unknown)}")
    missing = sorted(set(known) - set(values))
    if missing:
        raise ConfigError(f"[{name}] is missing required key(s): {', '.join(missing)}")
    coerced: dict[str, Any] = {}
    for key, value in values.items():
        annotation = str(known[key])
        if annotation.startswith("tuple"):
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ConfigError(f"{name}.{key} must be a list of strings")
            coerced[key] = tuple(value)
        elif annotation == "bool":
            if not isinstance(value, bool):
                raise ConfigError(f"{name}.{key} must be true or false")
            coerced[key] = value
        elif annotation == "int":
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ConfigError(f"{name}.{key} must be a positive integer")
            coerced[key] = value
        else:
            if not isinstance(value, str):
                raise ConfigError(f"{name}.{key} must be a string")
            coerced[key] = value
    return cls(**coerced)


def _enum(section: str, key: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ConfigError(f"{section}.{key} must be one of {', '.join(allowed)}; got {value!r}")


def _budgets(raw: dict[str, Any], preset: dict[str, Any]) -> Budgets:
    configured = _table(raw, "budgets")
    unknown = sorted(set(configured) - set(Budgets.NAMES))
    if unknown:
        raise ConfigError(f"[budgets] has unknown key(s): {', '.join(unknown)}")
    for key, value in configured.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ConfigError(f"budgets.{key} must be a positive integer")
    return Budgets(preset=dict(preset["budgets"]), configured=dict(configured))


def _personal(machine: Path, preset: dict[str, Any]) -> Personal:
    values: dict[str, Any] = dict(preset.get("defaults", {}).get("personal", {}))
    if machine.is_file():
        try:
            raw = tomllib.loads(machine.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{machine} is not valid TOML: {exc}") from None
        values.update(_table(raw, "personal"))
    return _build(Personal, "personal", values)


def load(root: Path, *, machine: Path | None = None) -> Config:
    path = root / CONFIG_FILE
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"{path} does not exist; run `keelline init` first") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from None
    unknown = sorted(set(raw) - set(SECTIONS))
    if unknown:
        raise ConfigError(f"{path} has unknown section(s): {', '.join(unknown)}")

    head = _table(raw, "keelline")
    preset_name = str(head.get("preset", "recommended"))
    preset = load_preset(preset_name)
    defaults = dict(preset.get("defaults", {}))
    defaults["keelline"] = {**defaults.get("keelline", {}), "preset": preset_name}

    keelline = _build(Keelline, "keelline", _merged(raw, defaults, "keelline"))
    _enum("keelline", "state", keelline.state, STATES)
    project = _build(Project, "project", _merged(raw, defaults, "project"))
    if not PROJECT_NAME.match(project.name):
        raise ConfigError(
            "project.name must be one lowercase path segment matching "
            f"{PROJECT_NAME.pattern}; got {project.name!r}"
        )
    paths = _build(Paths, "paths", _merged(raw, defaults, "paths"))
    memory = _build(Memory, "memory", _merged(raw, defaults, "memory"))
    _enum("memory", "mode", memory.mode, MEMORY_MODES)
    ledger = _build(Ledger, "ledger", _merged(raw, defaults, "ledger"))
    artifacts = _build(Artifacts, "artifacts", _merged(raw, defaults, "artifacts"))
    ci = _build(Ci, "ci", _merged(raw, defaults, "ci"))
    _enum("ci", "mode", ci.mode, CI_MODES)
    commit_messages = _build(
        CommitMessages, "commit_messages", _merged(raw, defaults, "commit_messages")
    )
    caps = _build(NativeCaps, "native_caps", dict(preset["native_caps"]))
    personal = _personal(machine or machine_config_path(), preset)
    config = Config(
        keelline=keelline,
        project=project,
        paths=paths,
        memory=memory,
        budgets=_budgets(raw, preset),
        native_caps=caps,
        ledger=ledger,
        artifacts=artifacts,
        ci=ci,
        commit_messages=commit_messages,
        personal=personal,
    )
    validate_paths(config, root)
    return config
