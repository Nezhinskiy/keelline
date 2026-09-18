"""Read keelline.toml, merge it under the preset, validate it.

The machine config (§5.4) is merged too, but it contributes `[personal]` and nothing else.
"""

from __future__ import annotations

import tomllib
from dataclasses import fields
from functools import cache
from pathlib import Path
from typing import Any, TypeVar, cast, get_origin, get_type_hints

from keelline import __version__
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


@cache
def _schema_types(cls: type[Any]) -> dict[str, Any]:
    """Real type objects for a schema class, resolved once per process.

    `get_type_hints` is what makes them real: under `from __future__ import annotations`
    `field.type` is only the source string, and dispatching on that string made every type the
    branches did not spell — `float`, `int | None`, an alias — silently "must be a string", so
    a valid config was refused with a wrong reason. Resolving costs an `eval` per annotation,
    which is why a load does not pay it nine times.
    """
    hints = get_type_hints(cls)
    return {f.name: hints[f.name] for f in fields(cls)}


def _build(cls: type[T], name: str, values: dict[str, Any]) -> T:
    known = _schema_types(cast(Any, cls))
    unknown = sorted(set(values) - set(known))
    if unknown:
        raise ConfigError(f"[{name}] has unknown key(s): {', '.join(unknown)}")
    missing = sorted(set(known) - set(values))
    if missing:
        raise ConfigError(f"[{name}] is missing required key(s): {', '.join(missing)}")
    coerced: dict[str, Any] = {}
    for key, value in values.items():
        annotation = known[key]
        if get_origin(annotation) is tuple:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ConfigError(f"{name}.{key} must be a list of strings")
            coerced[key] = tuple(value)
        elif annotation is bool:
            if not isinstance(value, bool):
                raise ConfigError(f"{name}.{key} must be true or false")
            coerced[key] = value
        elif annotation is int:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ConfigError(f"{name}.{key} must be a positive integer")
            coerced[key] = value
        elif annotation is str:
            if not isinstance(value, str):
                raise ConfigError(f"{name}.{key} must be a string")
            coerced[key] = value
        else:
            label = getattr(annotation, "__name__", None) or str(annotation)
            raise ConfigError(
                f"{name}.{key} has an unsupported schema type: {label}; "
                "the loader coerces tuple[str, ...], bool, int and str"
            )
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


def load(root: Path, *, machine: Path | None = None, interactive: bool | None = False) -> Config:
    """Read `keelline.toml` under the preset, and `[personal]` out of the machine file.

    `interactive` is threaded to `machine_config_path`, and exists because the seam was missing:
    `machine.py`'s docstring says "a caller that knows it is a hook, the MCP server or a
    `--gate` run says `interactive=False` rather than relying on the terminal check", and the
    one shipped non-interactive caller — `hooks.commands.run_hook` — had no way to say it.
    `load` called `machine_config_path()` with no argument, so the path the docstring singles
    out fell back to the `isatty` sniff. It evaluated `False` in practice, because a hook's
    stdin is a pipe, which means the gate held by circumstance rather than by construction.

    **It defaults to `False`, so that one command reads one machine file.** The sniff was the
    default, and `store.overlay_root` and `trust._trust_file` — the two anchors §9.1 and §9.4
    rest on — resolve that same file with `interactive=False` always. On an interactive run
    with `XDG_CONFIG_HOME` or `KEELLINE_CONFIG` set, the two disagreed: `[personal]` came from
    the owner's chosen file while `[overlay] root` and `trust.json` came from
    `~/.config/keelline/`, so an XDG-honouring owner who wrote one file with both tables got
    `[personal]` honoured and the overlay silently unrecorded — `keelline memory index`
    refusing with "no overlay root is recorded in the machine configuration; run `keelline
    setup`" about a file it had just read successfully.

    Half a file behind a gate is not a gate, exactly as `machine.py` says of one variable of a
    pair. So the whole file follows the stricter of the two rules, and `--machine` stays the
    supported way to name another one — honoured by all three readers, because it is a path a
    person typed rather than one an environment chose. `keelline doctor` is where an ignored
    `XDG_CONFIG_HOME` should be reported, which `machine.py`'s docstring already nominates it
    for.

    `None` asks for the sniff explicitly, and is what a future diagnostic would pass to say
    what *would* have been honoured.
    """
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
    personal = _personal(machine or machine_config_path(interactive=interactive), preset)
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


def preset_defaults(project: str, *, preset: str = "recommended") -> Config:
    """A `Config` built from a preset's `[defaults.*]` alone, for a directory that has no
    `keelline.toml` and never will.

    The overlay is a repository Keelline writes into and does not manage: it has no project
    configuration, and the scaffold engine needs one (it reads `keelline.profile` and
    `artifacts.local`, and nothing else). `init --yes` will want the same constructor for the
    first write into a project, before the file it would load exists.

    `keelline.version` is the one value the preset does not carry and `_build` requires: the
    engine stamps it into every manifest `Record`, so it comes from `keelline.__version__`
    rather than from a default that would record an empty string.

    `validate_paths` is deliberately not called. It is about a project root this caller does
    not have, and the `[paths]` values it would check are the preset's own defaults pointing at
    documents an overlay does not carry.
    """
    raw = load_preset(preset)
    defaults = dict(raw.get("defaults", {}))
    head = {**defaults.get("keelline", {}), "preset": preset, "version": __version__}
    return Config(
        keelline=_build(Keelline, "keelline", head),
        project=_build(Project, "project", {**defaults.get("project", {}), "name": project}),
        paths=_build(Paths, "paths", defaults.get("paths", {})),
        memory=_build(Memory, "memory", defaults.get("memory", {})),
        budgets=Budgets(preset=dict(raw.get("budgets", {}))),
        native_caps=_build(NativeCaps, "native_caps", dict(raw.get("native_caps", {}))),
        ledger=_build(Ledger, "ledger", defaults.get("ledger", {})),
        artifacts=_build(Artifacts, "artifacts", defaults.get("artifacts", {})),
        ci=_build(Ci, "ci", defaults.get("ci", {})),
        commit_messages=_build(
            CommitMessages, "commit_messages", defaults.get("commit_messages", {})
        ),
        personal=_build(Personal, "personal", defaults.get("personal", {})),
    )
