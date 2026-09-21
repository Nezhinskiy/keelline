from __future__ import annotations

from pathlib import Path

import pytest

from keelline.config.loader import CONFIG_FILE, ConfigError, load
from keelline.config.paths import PathEscape
from keelline.config.schema import Config
from keelline.errors import Failure, Refusal
from keelline.scaffold import Kind, Template, apply, plan

VALID_HEAD = """
[keelline]
version = "0.1.0"
state = "initialised"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"
"""

HOSTILE_PATHS = (
    VALID_HEAD
    + """
[paths]
agents_md = "../../AGENTS.md"
architecture = "../etc"
runbooks = "../runbooks"
adr = "../../adr"
specs = "../specs"
plans = "../plans"
bugs = "../bugs"
bug_index = "../bug-reports.md"
roadmap = "../roadmap.md"
roadmap_history = "../roadmap-history.md"
memory = "../memory"
"""
)

HOSTILE_FIELDS_SCAFFOLD_NEVER_READS = (
    VALID_HEAD
    + """
[memory]
mode = "local-only"
groups = ["../secret"]
index_extra = ["../../elsewhere/index.md"]

[ledger]
id_prefix = "BR"
code_roots = ["../../../../etc", "/etc/passwd"]
evidence_boundary_required_for = ["high"]
"""
)

HOSTILE_NAME = VALID_HEAD.replace('name = "widget"', 'name = "../common"')
HOSTILE_PRESET = VALID_HEAD.replace('preset = "recommended"', 'preset = "../../etc/passwd"')
HOSTILE_PROFILE = VALID_HEAD.replace('profile = ""', 'profile = "../../etc/passwd"')

ESCAPES = ["../../AGENTS.md", "/etc/keelline", "../runbooks/x.md", "docs/../../x.md", "", "."]


def write_config(root: Path, text: str) -> None:
    (root / CONFIG_FILE).write_text(text, encoding="utf-8")


def escaping_templates() -> list[Template]:
    return [
        Template(id=f"a{i}", kind=Kind.TEMPLATE, target=target, source="t", render=lambda: "x")
        for i, target in enumerate(ESCAPES)
    ]


def load_at(root: Path) -> Config:
    return load(root, machine=root / "absent.toml")


# --- the three fields C1 owns ---------------------------------------------------------------


def test_the_loader_refuses_every_escaping_paths_value(tmp_path: Path) -> None:
    write_config(tmp_path, HOSTILE_PATHS)
    with pytest.raises(PathEscape, match=r"\.\."):
        load_at(tmp_path)


def test_an_absolute_paths_value_is_refused_by_the_grammar_before_contained_is_reached() -> None:
    # Finding 5, fix round 1: with the `[paths]` grammar loop (P10, Task 1) running before any
    # `contained()` call, an absolute value like the one this fixture used to carry for
    # `architecture` is refused by the grammar first — `contained()`'s own `..`-shaped message
    # never fires for it, and folding it into `HOSTILE_PATHS` let one guard silently cover for
    # the other. Asserted directly against the grammar instead, so `HOSTILE_PATHS` above stays
    # every value `contained()` itself refuses.
    from keelline.config.schema import PATH_VALUE

    assert PATH_VALUE.match("/etc") is None


def test_the_loader_refuses_a_project_name_that_is_a_path(tmp_path: Path) -> None:
    write_config(tmp_path, HOSTILE_NAME)
    with pytest.raises(ConfigError, match=r"project\.name"):
        load_at(tmp_path)


def test_the_loader_refuses_a_preset_it_does_not_ship(tmp_path: Path) -> None:
    # `load_preset` raises Failure, ConfigError's parent. Asserting ConfigError here would
    # pass today only by accident and break the moment the message moved.
    write_config(tmp_path, HOSTILE_PRESET)
    with pytest.raises(Failure, match="preset"):
        load_at(tmp_path)


# --- the field C2 owns -----------------------------------------------------------------------


def test_the_engine_refuses_a_profile_the_loader_lets_through(tmp_path: Path) -> None:
    write_config(tmp_path, HOSTILE_PROFILE)
    config = load_at(tmp_path)
    assert config.keelline.profile == "../../etc/passwd"
    with pytest.raises(PathEscape, match="profile"):
        plan(tmp_path, config, escaping_templates())


def test_every_escaping_target_yields_zero_actions(tmp_path: Path) -> None:
    write_config(tmp_path, VALID_HEAD)
    result = plan(tmp_path, load_at(tmp_path), escaping_templates())
    assert result.actions == ()
    assert len(result.refusals) == len(ESCAPES)


def test_nothing_outside_the_root_is_written_even_when_apply_is_called(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    write_config(root, VALID_HEAD)
    with pytest.raises(Refusal):
        apply(root, plan(root, load_at(root), escaping_templates()))
    assert list(sibling.iterdir()) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["project", "sibling"]


# --- the two fields nobody guards yet ---------------------------------------------------------


def test_two_of_the_fixtures_own_fields_reach_no_guard_in_this_lane(tmp_path: Path) -> None:
    """§7.4 names `ledger.code_roots` and `memory.index_extra` contained targets, and this
    lane consumes neither: `config/paths.py`'s docstring hands them to whichever lane first
    reads them, which is `ledger` and `memory-engine`. Pinned here so the day one of them
    starts refusing, this assertion is the reminder that §7.4's fixture is finally whole."""
    write_config(tmp_path, HOSTILE_FIELDS_SCAFFOLD_NEVER_READS)
    config = load_at(tmp_path)
    assert config.ledger.code_roots == ("../../../../etc", "/etc/passwd")
    assert config.memory.index_extra == ("../../elsewhere/index.md",)
    assert config.memory.groups == ("../secret",)
