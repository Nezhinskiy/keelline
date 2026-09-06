"""Every `keelline.<area>.hooks.register()` result, in area-name order, with no shared list.

Nothing keys or de-duplicates handlers by their own name: two areas may register the same
handler name and both run.
"""

from __future__ import annotations

from keelline.areas import area_modules
from keelline.hooks.api import Handler


def discover() -> list[Handler]:
    handlers: list[Handler] = []
    for module in area_modules("hooks"):
        handlers.extend(module.register())
    return handlers
