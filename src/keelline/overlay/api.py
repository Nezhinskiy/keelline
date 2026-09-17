"""The overlay area's import surface: everything another lane may import from it.

`attach` (Wave C) reads `projects/<name>/project.toml` inside this layout and needs the names
for it; the release lane will need the template tree. A lane that needs something absent from
this list grows it deliberately, in a commit that says which lane and why — it does not import
a private module of this area.
"""

from keelline.overlay.layout import (
    COMMON,
    COMMON_CLAUDE,
    COMMON_CODEX,
    COMMON_MEMORY,
    COMMON_RULES,
    MARKETPLACE_MANIFEST,
    OVERLAY_FILES,
    PLUGIN_MANIFEST,
)
from keelline.overlay.template import template_root, templates

__all__ = [
    "COMMON",
    "COMMON_CLAUDE",
    "COMMON_CODEX",
    "COMMON_MEMORY",
    "COMMON_RULES",
    "MARKETPLACE_MANIFEST",
    "OVERLAY_FILES",
    "PLUGIN_MANIFEST",
    "template_root",
    "templates",
]
