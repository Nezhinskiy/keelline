# tests/setup/test_machine.py
from __future__ import annotations

import tomllib
from pathlib import Path

from keelline.config.loader import load
from keelline.memory.api import overlay_root
from keelline.presets import load_preset
from keelline.setup.api import read_machine, write_machine

# The minimal `keelline.toml` `load()` accepts: everything else comes from the preset's own
# defaults. `tests/hooks/test_hook_command.py::_initialised_project` carries the same shape for
# the same reason — a config load needs `[keelline]` and `[project]` and nothing more.
CONFIG = """
[keelline]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"
"""


def _initialised_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "keelline.toml").write_text(CONFIG, encoding="utf-8")
    return project


def test_the_file_written_is_the_file_both_readers_already_read(tmp_path: Path) -> None:
    # The whole point of DP5, asserted from the readers' side rather than the writer's: a
    # schema this writer invented would round-trip through its own reader and fail in a hook.
    path = tmp_path / "config.toml"
    write_machine(path, personal={"reply_language": "ru"}, overlay_root=tmp_path / "ov", machine={})
    assert overlay_root(path) == tmp_path / "ov"
    project = _initialised_project(tmp_path)
    assert load(project, machine=path).personal.reply_language == "ru"


def test_writing_without_an_overlay_leaves_no_overlay_table(tmp_path: Path) -> None:
    # `overlay_root` answering None must keep meaning "not recorded, and nothing else" — its
    # docstring spells out that an empty or broken table used to collapse six states into one
    # and produced wrong advice for three of them.
    path = tmp_path / "config.toml"
    write_machine(path, personal={}, overlay_root=None, machine={})
    assert overlay_root(path) is None
    assert "overlay" not in tomllib.loads(path.read_text(encoding="utf-8"))


def test_a_rewrite_preserves_a_value_this_run_did_not_set(tmp_path: Path) -> None:
    # A second `setup` on a machine that already has one is the common case. Losing the overlay
    # root because this run only set languages is the shape this catches.
    path = tmp_path / "config.toml"
    write_machine(path, personal={}, overlay_root=tmp_path / "ov", machine={})
    write_machine(path, personal={"reply_language": "ru"}, overlay_root=None, machine={})
    assert overlay_root(path) == tmp_path / "ov"
    assert read_machine(path)["personal"]["reply_language"] == "ru"


def test_a_hostile_value_cannot_write_a_second_key(tmp_path: Path) -> None:
    # The machine file records the overlay root — the anchor of the whole trust model. It is a
    # path the owner typed rather than repository bytes, but it travels through the same
    # serialiser as `project.toml`'s remote URL, and one escaping rule for both is the reason
    # `tomlout` exists rather than two format strings.
    #
    # Deviation from the plan's literal assertion, recorded rather than silently kept: the
    # brief's body reads `["artifact_language"] != "zz"`, which raises `KeyError` once the
    # value is escaped correctly — nothing here ever asked for a second key, so none is present
    # at all, and a bracket lookup cannot tell "escaped safely" from "never happened" apart
    # from "the naive concatenation this guards against". `.get(...)` reads the same intent —
    # no working `artifact_language = "zz"` key exists — without failing on the safe outcome
    # the escaping is supposed to produce. Mutation: format `reply_language` with an f-string
    # instead of `tomlout.dumps` → the naive concatenation closes the string early and this
    # test reddens on `== "zz"`.
    path = tmp_path / "config.toml"
    write_machine(
        path,
        personal={"reply_language": 'ru"\nartifact_language = "zz'},
        overlay_root=None,
        machine={},
    )
    assert read_machine(path)["personal"].get("artifact_language") != "zz"


def test_the_preset_names_the_plugins_and_the_deny_rules() -> None:
    # §5.6. superpowers is named because the design's own non-goal says so: "this is not a
    # replacement for superpowers. The recommended preset installs it."
    preset = load_preset("recommended")
    assert any("superpowers" in name for name in preset["plugins"]["install"])
    assert any(".env" in rule for rule in preset["deny"]["global"])
