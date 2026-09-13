from __future__ import annotations

import keelline.memory.api as memory


def test_the_c3_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # This list is the contract. A lane that needs something absent from it grows the list
    # deliberately, in a commit that says which lane and why — it does not import a private
    # module, and it does not get told after the fact that its import was a review finding.
    required = {
        "Bundle",
        "DELIMITER",
        "Fit",
        "IndexCheck",
        "Note",
        "NoteError",
        "NoteType",
        # `link` raises this and it carries `.created`; `attach` binds and links.
        "PartialLink",
        "Provenance",
        "Reconciliation",
        "SLOTS",
        "Store",
        "UnsafeNote",
        "Walk",
        "blocks",
        "check_index",
        "fit",
        # `inside_project` sends the reader to `in_repository` by name, `worktree` and
        # `bundles` both send them to `index_source`, and `attach` is the lane that creates
        # the symlinked index those two rules govern.
        "in_repository",
        "index_source",
        "INDEX_NAME",
        "inventory",
        "link",
        "linked_names",
        "markers",
        "may_inject",
        "new_nonce",
        "permitted_roots",
        "read_note",
        "reconcile",
        # `write_note` is on this list and `store_digest` covers every note, so a lane that
        # rewrites one in a trusted store revokes the record it depends on unless it can do
        # the same dance `memory index` does.
        "refresh_if_trusted",
        "Snapshot",
        "snapshot",
        "refusal_reason",
        "render",
        "render_index",
        "render_note",
        "resolve",
        "totals",
        "walk",
        "with_index",
        "wrap",
        "write_index",
    }
    assert required <= set(memory.__all__)


def test_the_export_list_is_exactly_what_the_module_imports_from_this_lane() -> None:
    # `assert getattr(memory, name) is not None` was the whole test, and every attribute a
    # module actually has is not None — it could not fail for any `__all__` this module is able
    # to import. What the contract needs asserting is the three ways the list and the imports
    # come apart: a name in `__all__` with no import behind it is an `AttributeError` at the
    # consumer, an import with no `__all__` entry is a name the contract does not really offer
    # (and `from ... import *` will not hand over), and an import from outside
    # `keelline.memory` would quietly make this module a back door into another area.
    import ast
    from pathlib import Path

    imported: set[str] = set()
    tree = ast.parse(Path(memory.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Import), "the surface re-exports, it does not import"
        if not isinstance(node, ast.ImportFrom) or node.module == "__future__":
            continue
        assert node.module is not None and node.module.startswith("keelline.memory.")
        imported |= {alias.asname or alias.name for alias in node.names}
    assert imported == set(memory.__all__)
    assert memory.__all__ == sorted(memory.__all__), "the contract list stays reviewable"
    for name in memory.__all__:
        assert hasattr(memory, name)


def test_the_surface_is_a_module_not_the_package_init() -> None:
    # Measured: with this list in `__init__.py`, `discover()` imports the whole area and
    # `tests/test_areas.py` goes red, because the hook registry imports the package first.
    import ast
    from pathlib import Path

    import keelline.memory

    init = Path(next(iter(keelline.memory.__path__))) / "__init__.py"
    tree = ast.parse(init.read_text(encoding="utf-8"))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom)]
