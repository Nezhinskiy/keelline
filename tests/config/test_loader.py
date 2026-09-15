from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from keelline.config.loader import CONFIG_FILE, ConfigError, _build, load
from keelline.config.paths import PathEscape

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
    with pytest.raises(ConfigError, match=r"project\.name"):
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
    # PathEscape is a Refusal (exit 2), not a ConfigError (exit 1): naming the class here is
    # what catches a regression that downgrades the refusal to a finding.
    write(tmp_path, MINIMAL + '\n[paths]\nspecs = "../elsewhere"\n')
    with pytest.raises(PathEscape, match="project root"):
        load(tmp_path, machine=tmp_path / "no-machine.toml")


def test_an_unsupported_schema_type_is_named_instead_of_read_as_a_string() -> None:
    # `_build` reads real types now, so a section a later lane adds with a `float`, an
    # `int | None` or an alias fails loudly here rather than being refused as "must be a
    # string" — a wrong reason nothing in the tests or the type checker would point at.
    @dataclass(frozen=True)
    class Sample:
        ratio: float

    with pytest.raises(ConfigError, match=r"sample\.ratio has an unsupported schema type: float"):
        _build(Sample, "sample", {"ratio": 1.5})


def test_load_can_be_told_it_is_not_interactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `machine.py`'s docstring: "a caller that knows it is a hook, the MCP server or a `--gate`
    # run says `interactive=False` rather than relying on the terminal check". `load` called
    # `machine_config_path()` with no argument, so the one shipped non-interactive caller had
    # no way to say it and fell back to the `isatty` sniff.
    home = tmp_path / "home"
    (home / ".config" / "keelline").mkdir(parents=True)
    (home / ".config" / "keelline" / "config.toml").write_text(
        '[personal]\nreply_language = "the-owners"\n', encoding="utf-8"
    )
    hostile = tmp_path / "hostile"
    (hostile / "keelline").mkdir(parents=True)
    (hostile / "keelline" / "config.toml").write_text(
        '[personal]\nreply_language = "the-repositorys"\n', encoding="utf-8"
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(hostile))

    root = tmp_path / "project"
    root.mkdir()
    (root / CONFIG_FILE).write_text(MINIMAL, encoding="utf-8")
    assert load(root, interactive=False).personal.reply_language == "the-owners"
    assert load(root, interactive=True).personal.reply_language == "the-repositorys"


def test_the_hook_path_says_it_is_not_interactive() -> None:
    # The seam is only worth having if the shipped caller uses it. Read off the source rather
    # than simulated, because the alternative — a hook invocation whose stdin is a tty — is not
    # a thing a test can arrange, and the `isatty` sniff answers correctly by accident.
    import inspect

    from keelline.hooks import commands

    assert "load(root, interactive=False)" in inspect.getsource(commands.run_hook)
