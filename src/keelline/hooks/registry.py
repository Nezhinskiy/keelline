"""Every `keelline.<area>.hooks.register()` result, by name, with no shared list to edit."""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil

import keelline
from keelline.hooks.api import Handler


def discover() -> list[Handler]:
    handlers: list[Handler] = []
    for module in sorted(pkgutil.iter_modules(keelline.__path__), key=lambda m: m.name):
        if not module.ispkg:
            continue
        spec = importlib.util.find_spec(f"keelline.{module.name}.hooks")
        if spec is None:
            continue
        handlers.extend(importlib.import_module(spec.name).register())
    return handlers
