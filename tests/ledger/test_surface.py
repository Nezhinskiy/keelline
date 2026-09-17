from __future__ import annotations

import keelline.ledger.api as ledger


def test_the_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # An equality, for the reason tests/guards/test_surface.py gives: a subset let an export
    # arrive unnoticed. No mutation entry: the mutation is adding an export (two lines).
    required = {
        "Entry",
        "LedgerError",
        "STATUSES",
        "SEVERITIES",
        "FIXTURE_MARKER",
        "ENTRIES_MISSING",
        "FOREIGN_CONTENT",
        "parse_entry",
        "load_entries",
        "render_index",
        "is_generated_index",
        "uninitialised",
        "problems",
        "next_identifier",
        "file_entry",
        "renumber",
    }
    assert required == set(ledger.__all__)


def test_the_export_list_is_exactly_what_the_module_imports_from_this_lane() -> None:
    import ast
    from pathlib import Path

    imported: set[str] = set()
    tree = ast.parse(Path(ledger.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Import), "the surface re-exports, it does not import"
        if not isinstance(node, ast.ImportFrom) or node.module == "__future__":
            continue
        assert node.module is not None and node.module.startswith("keelline.ledger.")
        imported |= {alias.asname or alias.name for alias in node.names}
    assert imported == set(ledger.__all__)
    for name in ledger.__all__:
        assert hasattr(ledger, name)


def test_the_surface_is_a_module_not_the_package_init() -> None:
    import ast
    from pathlib import Path

    import keelline.ledger

    init = Path(next(iter(keelline.ledger.__path__))) / "__init__.py"
    tree = ast.parse(init.read_text(encoding="utf-8"))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom)]
