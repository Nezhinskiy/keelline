from __future__ import annotations

import keelline.memory.api as memory


def test_the_c3_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # This list is the contract. A lane that needs something absent from it grows the list
    # deliberately, in a commit that says which lane and why — it does not import a private
    # module, and it does not get told after the fact that its import was a review finding.
    required = {
        "Bundle",
        "Note",
        "NoteType",
        "Provenance",
        "SLOTS",
        "Store",
        "blocks",
        "check_index",
        "fit",
        "inventory",
        "link",
        "linked_names",
        "may_inject",
        "permitted_roots",
        "read_note",
        "reconcile",
        "refusal_reason",
        "render",
        "render_index",
        "render_note",
        "resolve",
        "totals",
        "walk",
        "write_index",
    }
    assert required <= set(memory.__all__)


def test_every_exported_name_resolves() -> None:
    for name in memory.__all__:
        assert getattr(memory, name) is not None


def test_the_surface_is_a_module_not_the_package_init() -> None:
    # Measured: with this list in `__init__.py`, `discover()` imports the whole area and
    # `tests/test_areas.py` goes red, because the hook registry imports the package first.
    import ast
    from pathlib import Path

    import keelline.memory

    init = Path(next(iter(keelline.memory.__path__))) / "__init__.py"
    tree = ast.parse(init.read_text(encoding="utf-8"))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom)]
