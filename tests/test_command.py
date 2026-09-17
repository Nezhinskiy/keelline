from __future__ import annotations

import argparse
from pathlib import Path

from keelline.command import common_flags, root_and_config

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


def test_common_flags_are_root_and_machine_and_store_only_on_request() -> None:
    plain = common_flags(argparse.ArgumentParser())
    assert vars(plain.parse_args([])) == {"root": ".", "machine": None}
    with_store = common_flags(argparse.ArgumentParser(), store=True)
    assert vars(with_store.parse_args(["--store", "s"])) == {
        "root": ".",
        "machine": None,
        "store": "s",
    }


def test_root_and_config_resolves_the_root_and_loads_under_the_named_machine_file(
    tmp_path: Path,
) -> None:
    root = tmp_path / "widget"
    root.mkdir()
    (root / "keelline.toml").write_text(CONFIG, encoding="utf-8")
    args = common_flags(argparse.ArgumentParser()).parse_args(
        ["--root", str(root), "--machine", str(tmp_path / "m.toml")]
    )
    resolved, config = root_and_config(args)
    assert resolved == root.resolve() and config.project.name == "widget"
