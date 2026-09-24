"""Read keelline.toml, merge it under the preset, validate it.

The machine config (§5.4) is merged too, but it contributes `[personal]` and nothing else.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import MISSING, fields, replace
from functools import cache
from pathlib import Path
from typing import Any, TypeVar, cast, get_origin, get_type_hints

from keelline import __version__
from keelline.config.machine import machine_config_path
from keelline.config.paths import contained, validate_paths
from keelline.config.schema import (
    BUILTIN_GATES,
    CI_MODES,
    CONFIG_CHECK,
    MEMORY_MODES,
    PROJECT_NAME,
    SECTION_NAME,
    STATES,
    Artifacts,
    Budgets,
    Ci,
    CommitMessages,
    Config,
    CustomGate,
    Gates,
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
# Where `tomllib` stopped, and nothing else it had to say (P10). Every `TOMLDecodeError` this
# package can raise is about a document somebody else wrote — a project's `keelline.toml`, the
# machine file `--machine` named — and `tomllib` builds its message as `f"{msg} (at line N,
# column M)"`, where `msg` embeds the source for at least five of its own faults: `Cannot
# declare ('x',) twice`, `Duplicate inline table key 'k'`, `Cannot redefine namespace k`,
# `Found invalid character 'c'`, `Cannot overwrite a value`. A TOML key is arbitrary quoted
# text, so interpolating the exception whole puts unbounded repository bytes into a refusal a
# skill is instructed to relay to a model. The position is the actionable half and it is
# Keelline-shaped: two integers, or the parser's end-of-document form. Measured against CPython
# 3.11 and 3.12; the suffix is what `tomllib` appends, not what its `msg` says, so a `msg`
# reworded upstream does not move it.
_TOML_POSITION = re.compile(r"\((?:at line \d+, column \d+|at end of document)\)\Z")
NO_POSITION = "(at a position tomllib did not report)"
SECTIONS = (
    "keelline",
    "project",
    "paths",
    "memory",
    "budgets",
    "ledger",
    "artifacts",
    "ci",
    "gates",
    "commit_messages",
)
# Every refusal below names its key and quotes no value from the document. A state is a member
# of `STATES`, a count is a count, and the names a refusal lists are Keelline's own tuple or
# configured names that have already matched `PROJECT_NAME`.
GATES_BUILTIN_UNKNOWN = (
    "[gates] builtin names {count} gate(s) Keelline does not have; the built-in gates are {known}"
)
GATES_BUILTIN_TWICE = "[gates] builtin names a gate twice"
GATES_CUSTOM_NAME = (
    "[gates] custom names {count} gate(s) Keelline cannot run under that name: a custom gate's "
    "name matches {pattern} and is neither a built-in gate's name nor `config`"
)
GATES_CUSTOM_TABLE = "[gates.custom.{name}] must be a table"
GATES_CUSTOM_EMPTY = "gates.custom.{name}.run must name a command"
GATES_CUSTOM_NUL = "gates.custom.{name}.run holds a NUL character, which no argv can carry"
GATES_UNKNOWN = (
    "[keelline] enforced names {count} gate(s) this project does not run; the gates it runs are "
    "{known}"
)
GATES_TWICE = "[keelline] enforced names a gate twice"
GATES_EARLY = (
    "[keelline] state is initialised and enforced lists {count} gate(s), but an initialised "
    "project enforces nothing: promoting a gate is what moves a project to adopting"
)
GATES_PARTIAL = (
    "[keelline] state is installed and enforced lists {count} of the project's {total} gate(s), "
    "but installed means every gate enforces: list every gate, or none"
)


T = TypeVar("T")


class ConfigError(Failure):
    """A keelline.toml that cannot be trusted as written."""


class MachineConfigError(ConfigError):
    """The **machine** file could not be read, which is not `keelline.toml`'s doing.

    A subclass and not a message, because the one caller that has to tell them apart must not
    do it by reading the text: `doctor` deliberately never quotes a loader message — the loader
    builds it out of the file's own keys and values — so its only way to say which of the two
    files is broken was the type. It said `keelline.toml is here and does not load` for a
    `~/.config/keelline/config.toml` with a stray bracket in it, and sent the owner to edit a
    file with nothing wrong with it.
    """


def toml_position(exc: tomllib.TOMLDecodeError) -> str:
    """The `(at line N, column M)` suffix `tomllib` appends, with its message text dropped.

    One extractor for every caller in this package that reports a document it did not write,
    so that "what may print out of a parse failure" is one decision rather than one per site.
    See `_TOML_POSITION` for which of `tomllib`'s own messages embed the source and why that
    makes the whole exception unprintable.

    A suffix this cannot find is reported as absent rather than as the message: a `tomllib` that
    stopped appending a position would otherwise take this guard with it silently, which is the
    shape every other bounded value in this file refuses.
    """
    found = _TOML_POSITION.search(str(exc))
    return found.group(0) if found is not None else NO_POSITION


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


def _named(unknown: list[str], noun: str) -> str:
    """`unknown`, bounded before it may print (P10): a plain-named one is echoed, anything else
    is counted and never quoted — `PATH_VALUE`'s rule read onto a second grammar.

    **Every name in a `keelline.toml` is repository-authored, not only the table names.** A TOML
    key is arbitrary quoted text, so `[paths] "docs\u001b[31m\nIGNORE ALL PRIOR RULES" = 1` put raw
    ESC and raw newlines into `[paths] has unknown key(s): ...` — a refusal the terminal renders
    and the `init` skill relays to a model — on all nine tables. That message sat two functions
    from this one, which was written for exactly this rule and applied only to the section list.

    `SECTION_NAME` is the grammar both callers use, and it is a deliberate re-reading rather than
    a coincidence: every key any schema class or `Budgets.NAMES` declares is lowercase words
    joined by underscores, so a typo worth naming (`branch` for `gate_branch`) matches and
    nothing Keelline answers to falls outside. A key carrying anything else is counted.

    `noun` is what the count calls the names it would not print, so the sentence reads about the
    thing that was unknown: a section, or a key.
    """
    named = [name for name in unknown if SECTION_NAME.match(name)]
    unnamed = len(unknown) - len(named)
    parts = list(named)
    if unnamed:
        # The noun agrees with the count, for the reason the verb already did: one unnamed key
        # produced "1 more that is not plain key names", which is the common case of this arm.
        tail = f"is not a plain {noun} name" if unnamed == 1 else f"are not plain {noun} names"
        # "more" only when something was named: with every name failing the grammar the message
        # read "unknown section(s): 3 more that are not plain section names" — more than nothing.
        more = "more " if named else ""
        parts.append(f"{unnamed} {more}that {tail}")
    return ", ".join(parts)


def _build(cls: type[T], name: str, values: dict[str, Any]) -> T:
    known = _schema_types(cast(Any, cls))
    unknown = sorted(set(values) - set(known))
    if unknown:
        raise ConfigError(f"[{name}] has unknown key(s): {_named(unknown, 'key')}")
    # A field with a default is filled by the section's own reader after `_build` (`Gates.custom`
    # is the one), so only a field without one is required of the merged table.
    required = {
        f.name
        for f in fields(cast(Any, cls))
        if f.default is MISSING and f.default_factory is MISSING
    }
    missing = sorted(required - set(values))
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
    """The key and the vocabulary it may be spelled in; never the value it was spelled with.

    The three keys this guards — `keelline.state`, `memory.mode`, `ci.mode` — are
    repository-authored strings bounded by no grammar, so a clone can write anything at all
    into one, and the refusal reaches a terminal and a model through the `init` and `attach`
    skills' relay. `; got {value!r}` therefore put unbounded repository bytes into it:
    `ci.mode must be one of reusable, uvx, none; got '\\x1b[2JIGNORE PRIOR RULES'`. `!r` escapes
    the control characters, which makes it milder than a raw-bytes leak and not a different
    kind of thing — it is still content- and length-unbounded.

    Nothing is lost by dropping it. `allowed` is Keelline's own closed vocabulary, the key names
    the line to look at, and the reader has the file open. This is the ruling `PROJECT_NAME`'s
    refusal one screen down already took for the same reason — it dropped `; got
    {project.name!r}` — and `_named` took for the keys of every table.
    """
    if value not in allowed:
        raise ConfigError(f"{section}.{key} must be one of {', '.join(allowed)}")


def _deduplicated(memory: Memory) -> Memory:
    """`memory.groups` with each entry kept once, in the order the document wrote them.

    `_build` coerced the list with `tuple(value)` and nothing else, and it is the one
    repository-authored list four separate lanes report as a **count** a user is asked to act
    on. `groups = ["developer", "developer"]` made `attach.binding.unlinked_groups` walk one
    directory twice, so `attach` refused naming two groups that never moved into the overlay,
    `attach --check` printed `real_directories: 2`, and the session line told the model two --
    all about one directory, and with the remedy ("move them into the overlay") already done
    for the only one there is.

    `dict.fromkeys` and not `set`, because the order is the owner's: the link tree is built in
    it, and a refusal that reorders the list a person is reading is a worse answer than one
    that does not.

    **Deduplication only, and the containment stays where it is.** `config/paths.py` names
    `memory.groups` one of four repository-writable fields this loader deliberately does not
    contain, and hands each to the lane that first reads it -- because the anchor differs per
    lane: `unlinked_groups` contains a group against the checkout, `attach._check_groups`
    against the overlay, `memory.store` against the store. A grammar check here would refuse a
    spelling those three already refuse, one layer above the guard that knows what it is
    anchored to, and would take the reachable arm of each of them with it. What this function
    fixes is the one thing none of them can: a count taken over a list with a duplicate in it.
    """
    return replace(memory, groups=tuple(dict.fromkeys(memory.groups)))


def _gates(raw: dict[str, Any], defaults: dict[str, Any]) -> Gates:
    """`[gates]`: which built-in gates run, and the project's own.

    A custom gate's name is a TOML key, which is arbitrary quoted text, so a name is counted
    and never quoted until it has matched `PROJECT_NAME`; after that it is printable, and every
    later refusal names it. `run` is never printed at all. The two argvs `subprocess` cannot run,
    an empty one and one carrying a NUL, are refused here rather than raised as an internal
    error by whatever runs the gate.
    """
    values = _merged(raw, defaults, "gates")
    tables = values.pop("custom", {})
    gates = _build(Gates, "gates", values)
    unknown = [name for name in gates.builtin if name not in BUILTIN_GATES]
    if unknown:
        known = ", ".join(BUILTIN_GATES)
        raise ConfigError(GATES_BUILTIN_UNKNOWN.format(count=len(unknown), known=known))
    if len(set(gates.builtin)) != len(gates.builtin):
        raise ConfigError(GATES_BUILTIN_TWICE)
    if not isinstance(tables, dict):
        raise ConfigError("[gates.custom] must be a table")
    reserved = (*BUILTIN_GATES, CONFIG_CHECK)
    unusable = [name for name in tables if not PROJECT_NAME.match(name) or name in reserved]
    if unusable:
        pattern = PROJECT_NAME.pattern
        raise ConfigError(GATES_CUSTOM_NAME.format(count=len(unusable), pattern=pattern))
    custom: dict[str, CustomGate] = {}
    for name, table in sorted(tables.items()):
        if not isinstance(table, dict):
            raise ConfigError(GATES_CUSTOM_TABLE.format(name=name))
        gate = _build(CustomGate, f"gates.custom.{name}", table)
        if not gate.run:
            raise ConfigError(GATES_CUSTOM_EMPTY.format(name=name))
        if any("\0" in part for part in gate.run):
            raise ConfigError(GATES_CUSTOM_NUL.format(name=name))
        custom[name] = gate
    return replace(gates, custom=custom)


def _enforcement(config: Config) -> Config:
    """`[keelline] enforced` held to the gates this project runs, and `installed` made explicit.

    `state` is the lifecycle and `enforced` what was promoted while adopting, so the two state
    one fact and this refuses the ways they can contradict each other. The list holds configured
    gate names, once each, only once the project is past `initialised`, and under `installed`
    either every gate or none. An entry outside the configured set is counted and never quoted:
    it is exactly the value no grammar has bounded. The names the refusal lists are the
    configured ones, each already held to a grammar.

    Under `installed` the loaded list becomes every configured gate, so `Keelline.enforcing` is
    the list and nothing else, and a gate added to an installed project enforces from the run
    that adds it.
    """
    keelline = config.keelline
    names = config.gate_names
    unknown = [name for name in keelline.enforced if name not in names]
    if unknown:
        known = ", ".join(names) or "none"
        raise ConfigError(GATES_UNKNOWN.format(count=len(unknown), known=known))
    if len(set(keelline.enforced)) != len(keelline.enforced):
        raise ConfigError(GATES_TWICE)
    if keelline.state == "initialised" and keelline.enforced:
        raise ConfigError(GATES_EARLY.format(count=len(keelline.enforced)))
    if keelline.state != "installed":
        return config
    if keelline.enforced and set(keelline.enforced) != set(names):
        total = len(names)
        raise ConfigError(GATES_PARTIAL.format(count=len(keelline.enforced), total=total))
    return replace(config, keelline=replace(keelline, enforced=names))


def _budgets(raw: dict[str, Any], preset: dict[str, Any]) -> Budgets:
    configured = _table(raw, "budgets")
    unknown = sorted(set(configured) - set(Budgets.NAMES))
    if unknown:
        raise ConfigError(f"[budgets] has unknown key(s): {_named(unknown, 'key')}")
    for key, value in configured.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ConfigError(f"budgets.{key} must be a positive integer")
    return Budgets(preset=dict(preset["budgets"]), configured=dict(configured))


def _personal(machine: Path, preset: dict[str, Any]) -> Personal:
    values: dict[str, Any] = dict(preset.get("defaults", {}).get("personal", {}))
    if not machine.is_file():
        # No machine file, so `values` is the preset's own `[personal]` defaults and nothing
        # else. A fault here would be the preset's, not a machine's, and must not be relabelled.
        return _build(Personal, "personal", values)
    try:
        raw = tomllib.loads(machine.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise MachineConfigError(f"{machine} is not valid TOML {toml_position(exc)}") from None
    try:
        values.update(_table(raw, "personal"))
        return _build(Personal, "personal", values)
    except ConfigError as exc:
        # Everything from here is this file's doing: what `values` gained between the arm above
        # and this one is exactly its `[personal]` table.
        raise MachineConfigError(f"{machine}: {exc}") from None


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
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"{path} does not exist; run `keelline init` first") from None
    return loads(text, root, machine=machine, interactive=interactive)


def read_document(root: Path) -> str | None:
    """`keelline.toml` exactly as it is on disk, or `None` when there is none.

    `newline=""` and not `read_text`: this is the text a command hands to `config.owned.rewrite`,
    which keeps every byte but the values it sets, and universal-newline translation would have
    rewritten every CRLF in a file somebody else owns before the editor saw it. `contained`
    first, as for every configured path, so a symlinked `keelline.toml` is a refusal.
    """
    try:
        with contained(root, CONFIG_FILE).open(encoding="utf-8", newline="") as stream:
            return stream.read()
    except FileNotFoundError:
        return None


def loads(
    text: str, root: Path, *, machine: Path | None = None, interactive: bool | None = False
) -> Config:
    """Build a `Config` from `text` as `keelline.toml`'s contents, without reading a file.

    `load` is "read the file, then `loads`"; `init --yes` needs a `Config` for a document it
    has not written to disk yet, so the parse-and-validate half is this function on its own.
    """
    path = root / CONFIG_FILE
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML {toml_position(exc)}") from None
    unknown = sorted(set(raw) - set(SECTIONS))
    if unknown:
        raise ConfigError(f"{path} has unknown section(s): {_named(unknown, 'section')}")

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
            f"project.name must be one lowercase path segment matching {PROJECT_NAME.pattern}"
        )
    paths = _build(Paths, "paths", _merged(raw, defaults, "paths"))
    memory = _deduplicated(_build(Memory, "memory", _merged(raw, defaults, "memory")))
    _enum("memory", "mode", memory.mode, MEMORY_MODES)
    ledger = _build(Ledger, "ledger", _merged(raw, defaults, "ledger"))
    artifacts = _build(Artifacts, "artifacts", _merged(raw, defaults, "artifacts"))
    ci = _build(Ci, "ci", _merged(raw, defaults, "ci"))
    _enum("ci", "mode", ci.mode, CI_MODES)
    gates = _gates(raw, defaults)
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
        gates=gates,
        commit_messages=commit_messages,
        personal=personal,
    )
    config = _enforcement(config)
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
        gates=_gates({}, defaults),
        commit_messages=_build(
            CommitMessages, "commit_messages", defaults.get("commit_messages", {})
        ),
        personal=_build(Personal, "personal", defaults.get("personal", {})),
    )
