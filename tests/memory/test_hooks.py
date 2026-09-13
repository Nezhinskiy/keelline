from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from keelline.config.loader import CONFIG_FILE, load
from keelline.hooks.api import EVENTS, Decision, HookEvent, Policy
from keelline.memory import worktree as worktree_module
from keelline.memory.hooks import register

ROOT = Path(__file__).resolve().parents[2]
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

[memory]
mode = "local-only"
groups = ["developer"]
index_extra = []
"""

LIST_IMPORTS = (
    "import sys\n"
    "from keelline.hooks.registry import discover\n"
    "names = [h.name for h in discover()]\n"
    "assert 'worktree-link' in names, names\n"
    "print(' '.join(sorted(m for m in sys.modules if m.startswith('keelline'))))\n"
)


def an_event(root: Path, name: str = "SessionStart") -> HookEvent:
    return HookEvent(
        name=name,
        session_id="s1",
        agent_id=None,
        tool_name=None,
        tool_input={},
        cwd=root,
        project_root=root,
        harness="claude",
    )


def a_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / ".keelline" / "local" / "memory" / "developer").mkdir(parents=True)
    (root / CONFIG_FILE).write_text(CONFIG, encoding="utf-8")
    return root


def test_every_handler_declares_a_known_event_and_an_open_policy() -> None:
    handlers = register()
    assert handlers != []
    for handler in handlers:
        assert handler.event in EVENTS
        assert handler.policy is Policy.OPEN


def test_no_session_start_context_handler_is_registered() -> None:
    # The four injection bundles are `hooks.json` entries, not handlers: foundation's
    # dispatcher joins every handler's context for one event and clamps the join to a single
    # platform cap, which would collapse the numbered slots §9.5 exists to keep apart.
    names = [h.name for h in register() if h.event == "SessionStart"]
    assert names == ["worktree-link"]


def test_no_config_is_silence_not_an_exception(tmp_path: Path) -> None:
    for handler in register():
        result = handler.run(an_event(tmp_path), None)
        assert result.context is None
        assert result.decision is None


def test_a_broken_store_is_silence_not_an_exception(tmp_path: Path) -> None:
    root = a_project(tmp_path)
    (root / ".keelline" / "local" / "memory" / "developer" / "broken.md").write_text(
        "not frontmatter\n", encoding="utf-8"
    )
    config = load(root, machine=tmp_path / "absent.toml")
    for handler in register():
        assert handler.run(an_event(root), config).decision is None


def _raise(*_args: object, **_kwargs: object) -> list[Path]:
    raise RuntimeError("boom")


def test_a_link_failure_is_silence_not_an_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `test_a_broken_store_is_silence_not_an_exception` names the `try/except` as its guard,
    # but a note with bad frontmatter never reaches any code this handler runs: store
    # resolution and worktree linking only look at directory shape, never note bodies, and
    # `a_project`'s root is never a real git worktree, so `link` returns `[]` before touching
    # the filesystem at all. That test passes identically with the `try/except` removed. This
    # one forces the call `_link_worktree` makes after a store *does* resolve to fail outright,
    # so removing the guard actually reddens something.
    monkeypatch.setattr(worktree_module, "link", _raise)
    root = a_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    for handler in register():
        result = handler.run(an_event(root), config)
        assert result.decision is None
        assert result.context is None


def test_no_handler_in_this_area_ever_denies(tmp_path: Path) -> None:
    root = a_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    for handler in register():
        result = handler.run(an_event(root, handler.event), config)
        assert result.decision is not Decision.DENY


def test_discovery_does_not_import_the_configuration_layer() -> None:
    # `tests/test_areas.py` asserts this for the whole package; asserted here too, because it
    # is this area's own discipline that keeps it true — every config import lives inside a
    # handler body, and a module-level one would redden a test belonging to no wave-2 lane.
    done = subprocess.run(
        [sys.executable, "-c", LIST_IMPORTS],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src")},
    )
    assert done.returncode == 0, done.stderr
    imported = done.stdout.split()
    assert "keelline.memory.hooks" in imported
    assert "keelline.config" not in imported
    assert "keelline.presets" not in imported
