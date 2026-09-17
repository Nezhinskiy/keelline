"""`setup(preset, ...)`: the walkthrough's steps 3 and 4 (§4) — machine setup, once.

Five things, each reported and each independently skippable, in this order: write the machine
file (the personal defaults the preset names, and what this run installed); merge the preset's
deny rules and the personal values into the machine-scope settings file; install the preset's
plugins into every configured harness; report whether `keelline` itself resolves on `PATH`; and,
only when the caller named an answer, create or record the private overlay.

**Two harnesses, two verbs.** The spike record measured this rather than assuming symmetry:
Claude Code installs a plugin with `claude plugin install <name>@<marketplace>`, and Codex adds
one with `codex plugin add <name>@<marketplace>`. The spike record's Task 1 and Task 2 ran both
verbs against both CLIs (`docs/plans/2026-09-05-agent-harness-p0-spikes.md`). A harness this
module does not recognise gets a note rather than a guessed argv.

**`pluginConfigs` and not a flat top-level key.** Claude Code's own settings reference files a
plugin's non-sensitive `userConfig` answers under `pluginConfigs[<plugin-id>].options`, keyed by
`<plugin-name>@<marketplace-name>` and not by the plugin name alone — confirmed against
`code.claude.com/docs/en/settings-reference` before this was written, because a flatter shape
would round-trip through nothing Claude Code itself reads. `PLUGIN_ID` matches this repository's
own shipped manifest and marketplace names (`tests/test_manifests.py`), which is the pair this
plugin is actually installed under everywhere the preset's own `setup` runs.

**The overlay step is not gated behind `--yes`.** Reported rather than resolved: DP3 gates a
*write that widens a permission*, and recording a root, or creating a repository, is neither —
it happens only when the caller names `overlay=` an answer, which is this command's own
version of "an explicit confirmation flag" (the create branch also matches §6.1's "after
explicit confirmation" in as many words, since naming `create:<owner>/<name>` is the
confirmation). Whether that is the gate the plan means, or whether recording an overlay root
this way needs `--yes` on top of naming it, is called out in this wave's report rather than
decided here.
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
from keelline.overlay.api import Runner, create, init_instance
from keelline.presets import load_preset
from keelline.setup.machine import USER_SETTINGS, write_machine

# `<plugin-name>@<marketplace-name>`, matching `.claude-plugin/plugin.json`'s `name` and
# `.claude-plugin/marketplace.json`'s `name` (`tests/test_manifests.py` holds both). Claude
# Code keys `pluginConfigs` by this pair, not by the plugin name alone.
PLUGIN_ID = "keelline@keelline-marketplace"
# The release tag scheme (`vX.Y.Z`, §5.9); `uv tool install` has no `--from`, so the positional
# git URL form is the one D2 permits (`git+https://…@<tag>`).
INSTALL_COMMAND = "uv tool install git+https://github.com/Nezhinskiy/keelline@v{version}"


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


def _agents(preset: dict[str, Any]) -> tuple[str, ...]:
    agents = preset.get("defaults", {}).get("keelline", {}).get("agents", [])
    return tuple(agent for agent in agents if isinstance(agent, str))


def _install_argv(agent: str, selector: str) -> list[str] | None:
    """The argv that installs `selector` under `agent`, or `None` for a harness this does not
    recognise — reported as a note, never guessed at."""
    if agent == "claude":
        return ["claude", "plugin", "install", selector, "--scope", "user", "-y"]
    if agent == "codex":
        return ["codex", "plugin", "add", selector]
    return None


def _install_plugins(
    preset: dict[str, Any], agents: Sequence[str], *, home: Path, runner: Runner
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    selectors = [s for s in preset.get("plugins", {}).get("install", []) if isinstance(s, str)]
    installed: list[str] = []
    notes: list[str] = []
    for agent in agents:
        for selector in selectors:
            argv = _install_argv(agent, selector)
            if argv is None:
                notes.append(f"{agent}: no known plugin-install command; {selector} was skipped")
                continue
            # A missing binary is `Completed(127, ...)` from `Runner` itself (its own docstring:
            # "a missing binary is a finding, never a traceback"), so the non-zero branch below
            # covers both "not installed" and "installed but refused" with one message.
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


def _apply_overlay(overlay: str, *, home: Path, runner: Runner) -> tuple[Path, str]:
    """`home`, never `Path.cwd()`: this is a machine command, run from wherever the owner
    happened to be sitting, and a created overlay must not depend on that. Measured while
    writing this: `root=Path.cwd()` created a real `keelline-private/` inside this very
    checkout the first time a test exercised this branch, because the test's `tmp_path` was
    never in the call at all."""
    if overlay.startswith("create:"):
        spec = overlay[len("create:") :]
        owner, sep, name = spec.partition("/")
        if not sep or not owner or not name:
            raise Refusal(
                f"--overlay create:<owner>/<name> needs both a GitHub owner and a repository "
                f"name; got {overlay!r}"
            )
        created = create(owner, name, source="template", root=home, runner=runner)
        init_instance(created.root, owner, runner=runner)
        return created.root, f"created the overlay at {created.root}"
    root = Path(overlay).expanduser().resolve()
    return root, f"recorded the existing overlay at {root}"


def setup(
    preset: str,
    *,
    home: Path,
    machine: Path,
    runner: Runner,
    yes: bool,
    overlay: str | None,
) -> SetupReport:
    """Configure this machine from `preset`. `yes` takes the detected defaults for everything
    except the overlay: creating or recording one happens only when `overlay` names an answer,
    with or without `yes` (see the module docstring's note on this).

    `yes` is accepted and threaded through because the CLI contract names it and the skill's
    "use --yes only when the user asked for no prompts" is about the *agent* asking the person,
    not about a branch in here — nothing this task writes needs confirming beyond naming the
    overlay answer itself. A future write that does need it takes the parameter that is
    already here rather than growing the signature again.
    """
    # `home` is the root every write in this function lands under — the settings file through
    # `fsops.write_within` below, and a created overlay through `overlay.create` further down —
    # and it is not one this process was handed already existing, the way a project root or the
    # overlay itself is. Created directly for the same reason `setup.machine`'s module
    # docstring gives for `fsops.write_atomically` on the machine file: there is nothing for a
    # contained walk to be relative to until this directory exists.
    home.mkdir(parents=True, exist_ok=True)
    data = load_preset(preset)
    personal = _personal_defaults(data)
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
        overlay_root, note = _apply_overlay(overlay, home=home, runner=runner)
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
