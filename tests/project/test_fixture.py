"""The smoke fixture is what the shipped templates render (DC11).

The fixture is grown rather than generated at smoke time: `keelline init --yes --no-ci` ran on
a copy of it once, and the manifest and the footprint it wrote were committed back. So the
claim this module holds is the one that can go stale — that planning both passes over the
fixture today still has nothing to create, and that every artifact its manifest records is one
the plan recognises as already correct.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from keelline.config.loader import CONFIG_FILE, load
from keelline.project.api import project_templates
from keelline.release.api import Resolution
from keelline.scaffold import Manifest, Verb, plan

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "tests" / "fixtures" / "smoke-project"


def test_the_smoke_fixture_is_a_project_init_has_nothing_left_to_create_in(tmp_path: Path) -> None:
    # Mutation (by hand — the fixture is data): change one byte of the `documentation.md`
    # template -> `documentation-policy` leaves `unchanged` and the last assertion reddens,
    # and the fixture is regenerated (Task 12, Step 1). The fixture is what the templates
    # render.
    root = tmp_path / "smoke"
    shutil.copytree(SMOKE, root)
    config = load(root, machine=tmp_path / "absent.toml")
    document = (root / CONFIG_FILE).read_text(encoding="utf-8")
    prepared = project_templates(
        root, config, resolution=Resolution(None, True), document=document, adopted=True
    )
    once = plan(root, config, prepared.once)
    footprint = plan(root, config, prepared.footprint)
    # The walk is stated non-empty first: an empty artifact list would satisfy both assertions
    # below while proving nothing about the fixture at all.
    assert len(prepared.once) + len(prepared.footprint) >= 14
    assert not [a for a in [*once.actions, *footprint.actions] if a.verb is Verb.CREATE]
    recorded = set(Manifest.read(root).records)
    assert recorded and recorded <= set(footprint.unchanged) | set(once.unchanged) | {
        a.artifact_id for a in once.actions if a.verb is Verb.SKIP_MODIFIED
    }
