"""The overlay area's import surface: everything another lane may import from it.

`attach` (Wave C) reads `projects/<name>/project.toml` inside this layout and needs the names
for it, and reuses the `Runner` seam rather than shelling out of its own; the release lane will
need the template tree. A lane that needs something absent from this list grows it deliberately,
in a commit that says which lane and why — it does not import a private module of this area.
"""

from keelline.overlay.create import Created, Initialised, create, init_instance
from keelline.overlay.layout import (
    CAPABILITY_FILES,
    COMMON,
    COMMON_CLAUDE,
    COMMON_CODEX,
    COMMON_MEMORY,
    COMMON_RULES,
    MARKETPLACE_MANIFEST,
    OVERLAY_FILES,
    PLUGIN_MANIFEST,
)
from keelline.overlay.runner import Completed, Runner, subprocess_runner
from keelline.overlay.template import template_root, templates
from keelline.overlay.upgrade import OverlayUpgrade, upgrade

__all__ = [
    "CAPABILITY_FILES",
    "COMMON",
    "COMMON_CLAUDE",
    "COMMON_CODEX",
    "COMMON_MEMORY",
    "COMMON_RULES",
    "MARKETPLACE_MANIFEST",
    "OVERLAY_FILES",
    "PLUGIN_MANIFEST",
    "Completed",
    "Created",
    "Initialised",
    "OverlayUpgrade",
    "Runner",
    "create",
    "init_instance",
    "subprocess_runner",
    "template_root",
    "templates",
    "upgrade",
]
