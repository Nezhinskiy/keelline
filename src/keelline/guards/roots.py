"""`ledger.code_roots`, contained. `config.paths` guards `[paths]` and names this field as one
the consuming lane must check itself; two commands here consume it."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from keelline.config.paths import PathEscape, contained

if TYPE_CHECKING:
    from keelline.config.schema import Config


def contained_roots(root: Path, config: Config) -> list[Path]:
    """`ledger.code_roots` that pass `contained()` and exist as directories, in config order.

    `config.paths` says the four path-shaped fields it does not guard and names
    `ledger.code_roots` first; this is the call it asks the consuming lane to make.
    """
    found: list[Path] = []
    resolved_root = root.resolve()
    for entry in config.ledger.code_roots:
        try:
            candidate = contained(root, entry, resolved_root=resolved_root)
        except PathEscape:
            continue
        if candidate.is_dir():
            found.append(candidate)
    return found
