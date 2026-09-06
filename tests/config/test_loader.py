from __future__ import annotations

from pathlib import Path

import pytest

from keelline.config.loader import CONFIG_FILE, ConfigError, load

HEAD = '[keelline]\nversion = "0.1.0"\npreset = "recommended"\n'
MINIMAL = HEAD + '\n[project]\nname = "sample"\n'


def write(root: Path, text: str) -> None:
    (root / CONFIG_FILE).write_text(text, encoding="utf-8")


def test_missing_file_names_the_next_command(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="keelline init"):
        load(tmp_path, machine=tmp_path / "no-machine.toml")


def test_preset_defaults_fill_every_section(tmp_path: Path) -> None:
    write(tmp_path, MINIMAL)
    config = load(tmp_path, machine=tmp_path / "no-machine.toml")
    assert config.keelline.state == "initialised"
    assert config.paths.specs == "docs/specs"
    assert config.memory.mode == "local-only"
    assert config.budgets.effective("agents_md_lines") == 300
    assert config.native_caps.hook_output_chars == 10000
    assert config.commit_messages.types[-1] == "guard"
    assert config.personal.artifact_language == "en"


def test_file_values_override_preset_values(tmp_path: Path) -> None:
    write(
        tmp_path,
        MINIMAL + '\n[paths]\nspecs = "design/specs"\n\n[budgets]\nagents_md_lines = 250\n',
    )
    config = load(tmp_path, machine=tmp_path / "no-machine.toml")
    assert config.paths.specs == "design/specs"
    assert config.budgets.effective("agents_md_lines") == 250
    assert config.budgets.overrides == {"agents_md_lines": 250}


def test_machine_config_sits_between_file_and_preset(tmp_path: Path) -> None:
    write(tmp_path, MINIMAL)
    machine = tmp_path / "machine.toml"
    machine.write_text('[personal]\nreply_language = "ru"\n', encoding="utf-8")
    config = load(tmp_path, machine=machine)
    assert config.personal.reply_language == "ru"
    assert config.personal.artifact_language == "en"


def test_unknown_top_level_section_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, MINIMAL + "\n[commit]\nci_workflow = true\n")
    with pytest.raises(ConfigError, match=r"unknown section\(s\): commit"):
        load(tmp_path, machine=tmp_path / "no-machine.toml")


def test_unknown_key_inside_a_section_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, MINIMAL + '\n[ci]\nbranch = "dev"\n')
    with pytest.raises(ConfigError, match=r"\[ci\] has unknown key\(s\): branch"):
        load(tmp_path, machine=tmp_path / "no-machine.toml")


def test_a_section_that_is_not_a_table_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, 'ci = "not-a-table"\n' + MINIMAL)
    with pytest.raises(ConfigError, match=r"\[ci\] must be a table"):
        load(tmp_path, machine=tmp_path / "no-machine.toml")


@pytest.mark.parametrize("name", ["../common", "Ai Daybook", "", "-leading", "a/b"])
def test_project_name_must_be_one_lowercase_path_segment(tmp_path: Path, name: str) -> None:
    write(tmp_path, MINIMAL.replace('"sample"', f'"{name}"'))
    with pytest.raises(ConfigError, match="project.name"):
        load(tmp_path, machine=tmp_path / "no-machine.toml")


@pytest.mark.parametrize(
    ("text", "key"),
    [
        (HEAD + 'state = "deployed"\n\n[project]\nname = "sample"\n', "keelline.state"),
        (MINIMAL + '\n[memory]\nmode = "cloud"\n', "memory.mode"),
        (MINIMAL + '\n[ci]\nmode = "pip"\n', "ci.mode"),
    ],
)
def test_enumerated_values_are_validated(tmp_path: Path, text: str, key: str) -> None:
    write(tmp_path, text)
    with pytest.raises(ConfigError, match=key):
        load(tmp_path, machine=tmp_path / "no-machine.toml")


@pytest.mark.parametrize(
    "text",
    [
        MINIMAL + "\n[budgets]\nagents_md_lines = -5\n",
        MINIMAL + '\n[budgets]\nagents_md_lines = "many"\n',
        MINIMAL + '\n[commit_messages]\nattribution_check = "yes"\n',
        MINIMAL + '\n[ledger]\ncode_roots = "src"\n',
    ],
)
def test_value_types_and_ranges_are_validated(tmp_path: Path, text: str) -> None:
    write(tmp_path, text)
    with pytest.raises(ConfigError):
        load(tmp_path, machine=tmp_path / "no-machine.toml")


def test_a_path_that_escapes_the_root_is_refused_by_load(tmp_path: Path) -> None:
    write(tmp_path, MINIMAL + '\n[paths]\nspecs = "../elsewhere"\n')
    with pytest.raises(Exception, match="project root"):
        load(tmp_path, machine=tmp_path / "no-machine.toml")
