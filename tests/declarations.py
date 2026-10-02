"""The mutation oracle, loaded for the tests that read what `mutations/` declares.

`scripts/` is not an importable package, so the script is loaded by path. Here rather than in each
test that counts or walks the entries, so that every one of them reads the declarations the one way
the oracle does — `declared()`, over `group_files()` — and the directory's glob is spelled once, in
the script. `tests/scripts/test_mutation_oracle.py` loads fresh copies through `load` for the tests
that redirect the script's paths; everything else asks `declared()` here.
"""

from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mutation_oracle.py"


def load(name: str) -> ModuleType:
    """A fresh copy of the script under the module name `name`.

    Registered in `sys.modules` before it is executed: `@dataclass` resolves a field's
    annotations through `sys.modules[cls.__module__]`, and a module absent from there makes
    the decorator raise on `Mutation` itself.
    """
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module


@functools.cache
def _oracle() -> ModuleType:
    return load("mutation_oracle_declarations")


def declared() -> list[Any]:
    """Every entry `mutations/` declares, in the oracle's order, as its `Mutation`s."""
    return list(_oracle().declared())


def relative(path: Path) -> str:
    """An entry's `file` as the declaration spells it: from the repository root, with `/`."""
    return path.relative_to(SCRIPT.parents[1]).as_posix()
