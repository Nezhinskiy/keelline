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
    # The refusal is the grammar's now, and the fixture is unchanged: closing `.` and `..` as
    # segments — which a charset cannot do, because both are spelled out of characters a path
    # needs — means the `[paths]` grammar loop refuses every value here before `contained()` is
    # reached, exactly as it already did for the absolute one below. So this asserts what the
    # loop actually says: the key, and never the value. `contained()`'s own `..` refusal is not
    # covered for by this any more and is proven directly, in `tests/config/test_paths.py`:
    # `test_dotdot_is_refused_even_when_it_resolves_inside_the_root` and
    # `test_contained_refuses_every_spelling_the_write_would_refuse`.
    write_config(tmp_path, HOSTILE_PATHS)
    with pytest.raises(PathEscape) as caught:
        load_at(tmp_path)
    assert "paths.agents_md" in str(caught.value)
    assert "AGENTS.md" not in str(caught.value)


def test_an_absolute_paths_value_is_refused_by_the_grammar_before_contained_is_reached() -> None:
    # Finding 5, fix round 1: with the `[paths]` grammar loop (P10, Task 1) running before any
    # `contained()` call, an absolute value like the one this fixture used to carry for
    # `architecture` is refused by the grammar first — `contained()`'s own `..`-shaped message
    # never fires for it, and folding it into `HOSTILE_PATHS` let one guard silently cover for
    # the other. Asserted directly against the grammar instead.
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


# --- plan and apply agree about what a path is ------------------------------------------------

# Four spellings `plan()` used to pass and `apply()` then refused, and four it has always
# handled, in one list: the assertion below is that the two verdicts agree on every row, not
# that any particular row is refused.
ROUND_TRIP = (
    "docs/x.md",
    "AGENTS.md",
    ".keelline/local/x.md",
    "a.b-c/d_e.md",
    "docs//roadmap-history.md",
    "design/handbooks/",
    "./docs/x.md",
    "docs/./x.md",
    "docs/../x.md",
    "/etc/x",
    "",
    ".",
)


def test_a_target_that_survives_plan_is_one_apply_can_write(tmp_path: Path) -> None:
    # The round trip the suite did not have, which is why this survived four review rounds:
    # nothing asserted that a value `plan` reports no refusal for is a value `apply` can
    # actually write. `docs//roadmap-history.md` was the proof it could not — `plan` normalised
    # the empty component away through `Path(relative).parts`, `apply` split the raw string and
    # raised `UnsafePath` part-way through the pass, and `apply`'s `finally: manifest.write(root)`
    # then persisted a manifest for a run that had been refused. The repository was stuck after
    # that: `init` refuses a manifest it finds, and `upgrade` does not ship.
    #
    # Stated as an implication over every spelling rather than as a fixed expected verdict, so
    # it stays true for whatever the grammar and the component rule decide next.
    for index, target in enumerate(ROUND_TRIP):
        root = tmp_path / f"root-{index}"
        root.mkdir()
        write_config(root, VALID_HEAD)
        templates = [
            Template(id="only", kind=Kind.TEMPLATE, target=target, source="t", render=lambda: "x")
        ]
        planned = plan(root, load_at(root), templates)
        if planned.refusals:
            # A refused plan is allowed, and must have planned nothing and written nothing.
            assert planned.actions == ()
            assert not (root / ".keelline").exists(), target
            continue
        apply(root, planned)  # must not raise: this is the whole of the round trip
        assert (root / target).read_text(encoding="utf-8") == "x", target


def test_a_refused_paths_value_leaves_no_manifest_behind(tmp_path: Path) -> None:
    # The end-to-end consequence, through the `[paths]` table a clone actually commits. The
    # refusal now happens in the grammar loop `validate_paths` runs, above `contained()` and far
    # above the first write — so `init.py`'s "a refusal anywhere leaves nothing written and no
    # manifest" and `docs/cli.md`'s copy of it are true again.
    write_config(
        tmp_path,
        HOSTILE_PATHS.replace(
            'roadmap_history = "../roadmap-history.md"',
            'roadmap_history = "docs//roadmap-history.md"',
        ),
    )
    with pytest.raises(PathEscape):
        load_at(tmp_path)
    assert not (tmp_path / ".keelline").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == [CONFIG_FILE]


# --- git's control directory ------------------------------------------------------------------


def test_a_paths_value_inside_the_control_directory_is_refused_before_any_write(
    tmp_path: Path,
) -> None:
    # B2, end to end through the table a clone actually commits, and with the developer's own
    # hook on disk so the assertion is about the file and not only about the exception. The
    # `agents-md` artifact is a `MANAGED_REGION`, which the engine's "exists and Keelline did
    # not write it" guard exempts, so this reached `region_update` and `fsops._mode_of` carried
    # the existing 0755 onto the replacement.
    root = tmp_path / "project"
    (root / ".git" / "hooks").mkdir(parents=True)
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho real hook\n", encoding="utf-8")
    hook.chmod(0o755)
    write_config(
        root,
        VALID_HEAD + '\n[paths]\nagents_md = ".git/hooks/pre-commit"\n',
    )
    with pytest.raises(PathEscape, match="control directory"):
        load_at(root)
    assert hook.read_text(encoding="utf-8") == "#!/bin/sh\necho real hook\n"
    assert not (root / ".keelline").exists()
    assert sorted(p.name for p in (root / ".git").iterdir()) == ["hooks"]


def test_the_engine_refuses_a_control_directory_target_the_loader_never_sees(
    tmp_path: Path,
) -> None:
    # The second guard, on its own. A template target is not a `[paths]` value — the engine
    # builds it from `Location` and the artifact's own name — so it never passes through
    # `validate_paths`, and `contained()` is the only thing between it and the walk. Asserted
    # with a plan rather than through `load`, so this arm cannot be satisfied by the grammar
    # loop above it.
    write_config(tmp_path, VALID_HEAD)
    templates = [
        Template(
            id="hook",
            kind=Kind.TEMPLATE,
            target=".git/hooks/pre-commit",
            source="t",
            render=lambda: "x",
        )
    ]
    result = plan(tmp_path, load_at(tmp_path), templates)
    assert result.actions == ()
    assert [r.artifact_id for r in result.refusals] == ["hook"]
    assert "control directory" in result.refusals[0].reason


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
