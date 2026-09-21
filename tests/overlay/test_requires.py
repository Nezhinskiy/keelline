from __future__ import annotations

import json
from pathlib import Path

from keelline.overlay.api import requires_of, satisfies
from keelline.overlay.layout import PLUGIN_MANIFEST
from keelline.overlay.template import template_root


def overlay_with(root: Path, requires: object) -> Path:
    """An overlay directory whose manifest declares `requires`; shared with Task 5 and Task 6."""
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    body: dict[str, object] = {"name": "keelline-overlay", "version": "0.0.0"}
    if requires is not None:
        body["keelline"] = {"requires": requires}
    (root / PLUGIN_MANIFEST).write_text(json.dumps(body), encoding="utf-8")
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "keelline-overlay-marketplace", "plugins": []}), encoding="utf-8"
    )
    return root


def test_the_shipped_template_declares_a_floor_this_reader_reads() -> None:
    spec = requires_of(template_root())
    assert spec is not None and satisfies(spec, "0.1.0") is not None


def test_an_absent_declaration_and_an_absent_manifest_both_answer_none(tmp_path: Path) -> None:
    assert requires_of(overlay_with(tmp_path / "a", None)) is None
    assert requires_of(tmp_path / "nowhere") is None
    assert requires_of(overlay_with(tmp_path / "b", " >=0.1.0 ")) == ">=0.1.0"


def test_the_floor_is_compared_as_numbers_not_as_text() -> None:
    # Mutation (comment): compare `running.groups() >= floor.groups()` as strings -> the first
    # line reddens on `>=9.0.0` against `10.0.0`.
    assert satisfies(">=9.0.0", "10.0.0") is True
    assert satisfies(">=0.1.0", "0.1.0") is True
    assert satisfies(">=0.1.0", "0.0.9") is False


def test_any_other_form_is_unreadable_never_satisfied() -> None:
    for spec in ("~=1.0", ">1.0.0", "==0.1.0", ">=1.0", ">=a.b.c", ""):
        assert satisfies(spec, "0.1.0") is None, spec
    assert satisfies(">=0.1.0", "next") is None
