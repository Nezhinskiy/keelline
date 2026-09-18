"""`setup(preset, ...)`: the walkthrough's steps 3 and 4 (§4) — machine setup, once.

Five things, each reported and each independently skippable, in this order: write the machine
file (the personal defaults the preset names, for whichever of them nothing has recorded yet);
merge the preset's deny rules and the personal values into the machine-scope settings file;
register each preset plugin's marketplace and install from it, per configured harness; report
whether `keelline` itself resolves on `PATH`; and, only when the caller named an answer, create
or record the private overlay.

**A preset default never overwrites a value already recorded.** The first draft of this module
rebuilt `[personal]` from the preset's own defaults on every run, which meant a second
`setup --preset recommended` reset `reply_language` back to `""` even after the owner had set it
by hand — exactly the value `skills/setup/SKILL.md` calls "the user's to set" and
`setup.machine`'s own docstring promises survives a rewrite that "only set one of them" (Fix
round 1, item 1). `_new_personal_values` computes only the keys the machine file does not
already carry, and that is what both `write_machine` and the settings file's `pluginConfigs`
receive — an empty dict on every run after the first, once every key has a recorded value.

**Marketplaces are registered before anything is installed from them, and per-plugin sources
are never guessed.** The first draft attempted `claude plugin install superpowers@obra` on a
fresh machine and always failed there — `obra` and `upstash` are GitHub accounts, not
marketplace names, and every measured successful install in this tree's own spike record
(`docs/plans/2026-09-05-agent-harness-p0-spikes.md`) is preceded by a `marketplace add`
(Fix round 1, item 2). Checked before writing this fix (`gh api repos/...`, `claude plugin
marketplace list` on the machine this was written on): `superpowers` and `context7` both ship
in Anthropic's own official marketplace, `anthropics/claude-plugins-official`, which a Claude
Code install already carries — the `marketplace add` this module still issues is idempotent
defence in depth, not a first registration, and its own real output confirms that
(`✔ Marketplace 'claude-plugins-official' already on disk`). No non-interactive, non-guessed
source could be established for Codex, so nothing is attempted there for these two plugins; the
recommended preset's own `[plugins.claude]` table and the README carry the reasoning and the
recommendation respectively.

**Two harnesses, two verbs, and no unmeasured flags.** Claude Code installs a plugin with
`claude plugin install <name>@<marketplace>`, bare — the spike record's own transcript reports
`(scope: user)` as the *default* a bare install already gets, not something a flag adds, and
`-y` appears in that record only on `plugin uninstall`, never `install` (Fix round 1, item 3).
Codex adds one with `codex plugin add <name>@<marketplace>` when a marketplace is declared for
it — measured, not assumed, from this tree's own spike Task 1 and Task 2. A harness or a plugin
with no declared marketplace gets a note, never a guessed argv.

**`pluginConfigs` and not a flat top-level key.** Claude Code's own settings reference files a
plugin's non-sensitive `userConfig` answers under `pluginConfigs[<plugin-id>].options`, keyed by
`<plugin-name>@<marketplace-name>` and not by the plugin name alone — confirmed against
`code.claude.com/docs/en/settings-reference` before this was written, because a flatter shape
would round-trip through nothing Claude Code itself reads. `PLUGIN_ID` matches this repository's
own shipped manifest and marketplace names (`tests/test_manifests.py`), which is the pair this
plugin is actually installed under everywhere the preset's own `setup` runs.

**The overlay root is validated before it is ever trusted, and the create branch is gated on
`--yes`.** The coordinator's ruling on the named risk this wave's first report raised: `--yes`
on `--overlay <path>` would be theatre in a harness where the command line is written by a
model, so it is not added there. What bounds the exposure instead is that a recorded root must
exist, must carry the overlay's own published layout (`keelline.overlay.api`'s two manifests —
the same probe `overlay.create` already trusts), and must not lie inside the project root the
agent is working in — which removes the one case a hostile clone can actually stage: a tree it
ships alongside itself. `--yes` gets the one real control the ruling does give it: `setup`
refuses `--overlay create:<owner>/<name>` without it, because §6.1 asks for "explicit
confirmation" before `gh repo create` runs, and creating a repository on GitHub is the one
irreversible, outward-facing act this command performs.
"""

from __future__ import annotations

import datetime
import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from keelline import __version__, fsops
from keelline.errors import Failure, Refusal
from keelline.overlay.api import (
    MARKETPLACE_MANIFEST,
    PLUGIN_MANIFEST,
    Runner,
    create,
    init_instance,
)
from keelline.presets import load_preset
from keelline.setup.machine import USER_SETTINGS, read_machine, write_machine

# `<plugin-name>@<marketplace-name>`, matching `.claude-plugin/plugin.json`'s `name` and
# `.claude-plugin/marketplace.json`'s `name` (`tests/test_manifests.py` holds both). Claude
# Code keys `pluginConfigs` by this pair, not by the plugin name alone.
PLUGIN_ID = "keelline@keelline-marketplace"
# The release tag scheme (`vX.Y.Z`, §5.9); `uv tool install` has no `--from`, so the positional
# git URL form is the one D2 permits (`git+https://…@<tag>`).
INSTALL_COMMAND = "uv tool install git+https://github.com/Nezhinskiy/keelline@v{version}"
# One verb pair per harness, fixed here rather than in the preset: which CLI verb installs a
# plugin is a property of the harness, never of any one plugin, and the two differ (measured,
# Fix round 1 item 3's docstring paragraph above).
_MARKETPLACE_ADD = {
    "claude": lambda source: ["claude", "plugin", "marketplace", "add", source],
    "codex": lambda source: ["codex", "plugin", "marketplace", "add", source],
}
_PLUGIN_INSTALL = {
    "claude": lambda full: ["claude", "plugin", "install", full],
    "codex": lambda full: ["codex", "plugin", "add", full],
}


@dataclass(frozen=True)
class SetupReport:
    """What one `setup` run did. Every field here is this run's own computation, printable."""

    machine_written: bool
    plugins_installed: tuple[str, ...]
    deny_written: bool
    cli_on_path: bool
    overlay: Path | None
    notes: tuple[str, ...]


def _personal_defaults(preset: dict[str, Any]) -> dict[str, Any]:
    return dict(preset.get("defaults", {}).get("personal", {}))


def _existing_personal(machine: Path) -> dict[str, Any]:
    if not machine.is_file():
        return {}
    raw = read_machine(machine).get("personal")
    return dict(raw) if isinstance(raw, dict) else {}


def _new_personal_values(preset: dict[str, Any], machine: Path) -> dict[str, Any]:
    """The preset's personal defaults, minus every key the machine file already carries.

    A key present in the file — set by an earlier `setup`, or by the owner's own hand — is the
    owner's, and a preset default may not win over it on a later run. An absent key gets the
    preset's default, which is what makes a *first* run write all three (Fix round 1, item 1).
    """
    existing = _existing_personal(machine)
    return {k: v for k, v in _personal_defaults(preset).items() if k not in existing}


def _agents(preset: dict[str, Any]) -> tuple[str, ...]:
    agents = preset.get("defaults", {}).get("keelline", {}).get("agents", [])
    return tuple(agent for agent in agents if isinstance(agent, str))


def _marketplace(preset: dict[str, Any], agent: str) -> tuple[str, str] | None:
    """`(source, marketplace name)` for `agent`, or `None` when the preset declares none.

    `None` is not a fault: it is "nothing here is vendored for this harness on a guess" (§5.6),
    and the caller reports it as a note rather than attempting an argv nobody measured.
    """
    table = preset.get("plugins", {}).get(agent)
    if not isinstance(table, dict):
        return None
    source, marketplace = table.get("source"), table.get("marketplace")
    if not isinstance(source, str) or not isinstance(marketplace, str):
        return None
    return source, marketplace


def _install_plugins(
    preset: dict[str, Any], agents: Sequence[str], *, home: Path, runner: Runner
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    selectors = [s for s in preset.get("plugins", {}).get("install", []) if isinstance(s, str)]
    installed: list[str] = []
    notes: list[str] = []
    for agent in agents:
        market = _marketplace(preset, agent)
        if market is None:
            if selectors:
                notes.append(
                    f"{agent}: no verified marketplace for {', '.join(selectors)}; "
                    f"install manually if this harness supports it (see README)"
                )
            continue
        source, marketplace = market
        add_argv_of, install_argv_of = _MARKETPLACE_ADD.get(agent), _PLUGIN_INSTALL.get(agent)
        if add_argv_of is None or install_argv_of is None:
            notes.append(f"{agent}: no known plugin command for this harness")
            continue
        # Idempotent by construction: an already-registered source is a note from `claude`/
        # `codex` themselves ("already on disk"), read here through the same non-zero-is-a-note
        # path as everything else — a missing binary is `Completed(127, ...)` from `Runner`
        # itself (its own docstring: "a missing binary is a finding, never a traceback").
        added = runner.run(add_argv_of(source), home)
        if added.code != 0:
            detail = added.stderr.strip() or added.stdout.strip() or f"exit {added.code}"
            notes.append(f"{agent}: could not register marketplace {source} ({detail})")
            continue
        for selector in selectors:
            argv = install_argv_of(f"{selector}@{marketplace}")
            done = runner.run(argv, home)
            if done.code == 0:
                if selector not in installed:
                    installed.append(selector)
            else:
                detail = done.stderr.strip() or done.stdout.strip() or f"exit {done.code}"
                notes.append(f"{agent}: `{' '.join(argv)}` did not succeed ({detail})")
    return tuple(installed), tuple(notes)


def _read_document(path: Path) -> tuple[dict[str, Any], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, ""
    except OSError as exc:
        raise Failure(f"{path} cannot be read: {exc}") from exc
    if not text.strip():
        return {}, text
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise Failure(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise Failure(f"{path} is not a JSON object")
    return raw, text


def _write_user_settings(
    home: Path, deny_rules: Sequence[str], personal: Mapping[str, Any]
) -> bool:
    """Merge the preset's deny rules and the personal values into `<home>/<USER_SETTINGS>`.

    Merge, never replace: the owner's own file predates Keelline on most machines, and nothing
    this run did not add may be recorded as if it had. Deny only — this never reads or writes
    `permissions.allow` — and `pluginConfigs` gets the same treatment, key by key inside its own
    `options`, so a value this run did not set survives a second one same as `write_machine`'s.
    """
    path = home / USER_SETTINGS
    document, text = _read_document(path)

    permissions = document.get("permissions")
    permissions = dict(permissions) if isinstance(permissions, dict) else {}
    raw_deny = permissions.get("deny")
    existing_deny = (
        [r for r in raw_deny if isinstance(r, str)] if isinstance(raw_deny, list) else []
    )
    permissions["deny"] = existing_deny + [r for r in deny_rules if r not in existing_deny]
    document["permissions"] = permissions

    plugin_configs = document.get("pluginConfigs")
    plugin_configs = dict(plugin_configs) if isinstance(plugin_configs, dict) else {}
    entry = plugin_configs.get(PLUGIN_ID)
    entry = dict(entry) if isinstance(entry, dict) else {}
    options = entry.get("options")
    options = dict(options) if isinstance(options, dict) else {}
    options.update(personal)
    entry["options"] = options
    plugin_configs[PLUGIN_ID] = entry
    document["pluginConfigs"] = plugin_configs

    new_text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if new_text == text:
        return False
    fsops.write_within(home, USER_SETTINGS, new_text)
    return True


def _validate_overlay_root(candidate: Path, *, project_root: Path) -> None:
    """Refuse a root that is not really an overlay, or that sits where a clone could reach it.

    This is the wave's actual control over `--overlay <path>` (the coordinator's ruling on the
    named risk in the first report: `--yes` here would be theatre, since a model-written command
    line reaches `--overlay X --yes` exactly as easily as `--overlay X`). Two checks, both aimed
    at the one thing a hostile repository can actually stage:

    * **it must carry the overlay's own published layout** — the two manifests
      `keelline.overlay.api` names, the same pair `overlay.create`'s own probe and
      `overlay.init_instance`'s rename both already trust as "this is really an overlay". An
      empty directory, or one a clone shipped that merely *looks* plausible, fails this.
    * **it must not lie inside the project root** — equal to it, or nested under it. A path
      outside the repository that already carries a real overlay layout is not something a
      clone can create; a path inside it is exactly the shape of tree a clone can ship.
    """
    if not candidate.is_dir():
        raise Refusal(
            f"{candidate} is not a directory; --overlay must name an existing overlay's root"
        )
    missing = [f for f in (PLUGIN_MANIFEST, MARKETPLACE_MANIFEST) if not (candidate / f).is_file()]
    if missing:
        raise Refusal(
            f"{candidate} does not carry the overlay layout ({', '.join(missing)} missing); "
            f"--overlay must name a real overlay's root, not an arbitrary directory"
        )
    resolved_project = project_root.resolve()
    if candidate == resolved_project or resolved_project in candidate.parents:
        raise Refusal(
            f"{candidate} is inside {project_root}, the project this command was run from; "
            f"the overlay root is the machine's trust anchor and must live outside any "
            f"repository an agent works in — a repository could otherwise ship its own tree "
            f"and have this command record it"
        )


def _apply_overlay(
    overlay: str, *, home: Path, project_root: Path, yes: bool, runner: Runner
) -> tuple[Path, str]:
    """`home`, never `Path.cwd()`, for a *created* overlay: this is a machine command, run from
    wherever the owner happened to be sitting, and a created overlay must not depend on that.
    Measured while writing this: `root=Path.cwd()` created a real `keelline-private/` inside
    this very checkout the first time a test exercised this branch, because the test's
    `tmp_path` was never in the call at all.
    """
    if overlay.startswith("create:"):
        if not yes:
            raise Refusal(
                "creating a private overlay runs `gh repo create ... --private --template ...` "
                "on GitHub, which §6.1 permits only after explicit confirmation; pass --yes to "
                "confirm it, or use --overlay <path> to record one that already exists"
            )
        spec = overlay[len("create:") :]
        owner, sep, name = spec.partition("/")
        if not sep or not owner or not name:
            raise Refusal(
                f"--overlay create:<owner>/<name> needs both a GitHub owner and a repository "
                f"name; got {overlay!r}"
            )
        created = create(owner, name, source="template", root=home, runner=runner)
        init_instance(created.root, owner, runner=runner)
        _validate_overlay_root(created.root, project_root=project_root)
        return created.root, f"created the overlay at {created.root}"
    candidate = Path(overlay).expanduser().resolve()
    _validate_overlay_root(candidate, project_root=project_root)
    return candidate, f"recorded the existing overlay at {candidate}"


def setup(
    preset: str,
    *,
    home: Path,
    machine: Path,
    runner: Runner,
    yes: bool,
    overlay: str | None,
    project_root: Path,
) -> SetupReport:
    """Configure this machine from `preset`.

    `project_root` is the repository this invocation was run from (the CLI's `--root`, default
    `.`), and it exists for exactly one reason: `_validate_overlay_root` refuses an `--overlay`
    that lies inside it. `yes` takes the detected defaults for everything except creating an
    overlay, which needs it explicitly (see the module docstring).
    """
    # `home` is the root every write in this function lands under — the settings file through
    # `fsops.write_within` below, and a created overlay through `overlay.create` further down —
    # and it is not one this process was handed already existing, the way a project root or the
    # overlay itself is. Created directly for the same reason `setup.machine`'s module
    # docstring gives for `fsops.write_atomically` on the machine file: there is nothing for a
    # contained walk to be relative to until this directory exists.
    home.mkdir(parents=True, exist_ok=True)
    data = load_preset(preset)
    personal = _new_personal_values(data, machine)
    machine_table = {"version": __version__, "installed": datetime.date.today().isoformat()}
    write_machine(machine, personal=personal, overlay_root=None, machine=machine_table)

    deny_rules = [r for r in data.get("deny", {}).get("global", []) if isinstance(r, str)]
    deny_written = _write_user_settings(home, deny_rules, personal)

    installed, install_notes = _install_plugins(data, _agents(data), home=home, runner=runner)
    notes = list(install_notes)

    cli_on_path = shutil.which("keelline") is not None
    if not cli_on_path:
        notes.append(
            f"`keelline` is not on PATH; install it with "
            f"`{INSTALL_COMMAND.format(version=__version__)}`"
        )

    overlay_root: Path | None = None
    if overlay is not None:
        overlay_root, note = _apply_overlay(
            overlay, home=home, project_root=project_root, yes=yes, runner=runner
        )
        notes.append(note)
        write_machine(machine, personal={}, overlay_root=overlay_root, machine={})

    return SetupReport(
        machine_written=True,
        plugins_installed=installed,
        deny_written=deny_written,
        cli_on_path=cli_on_path,
        overlay=overlay_root,
        notes=tuple(notes),
    )
