from __future__ import annotations

import keelline.docs.api as docs


def test_the_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # The marker is here once, as `TRAIL_MARKER`: `docs.trail`'s `MARKER` is a module-local
    # alias for the same literal, and exporting both would put two names on one constant.
    required = {
        "TRAIL_MARKER",
        "STATUS_HEADING",
        "END_MARKER",
        "TRAIL_FILE",
        "Trail",
        "Lint",
        "check_budgets",
        "check_links",
        "check_memory_graph",
        "read_trail",
        "trail_path",
        "render_listing",
        "rebuild",
        "undeclared_new_documents",
        "lint",
    }
    assert required == set(docs.__all__)


def test_the_export_list_is_exactly_what_the_module_imports_from_this_lane() -> None:
    import ast
    from pathlib import Path

    imported: set[str] = set()
    tree = ast.parse(Path(docs.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Import)
        if not isinstance(node, ast.ImportFrom) or node.module == "__future__":
            continue
        assert node.module is not None and node.module.startswith("keelline.docs.")
        imported |= {alias.asname or alias.name for alias in node.names}
    assert imported == set(docs.__all__)


def test_the_surface_is_a_module_not_the_package_init() -> None:
    import ast
    from pathlib import Path

    import keelline.docs

    init = Path(next(iter(keelline.docs.__path__))) / "__init__.py"
    assert not [
        n
        for n in ast.walk(ast.parse(init.read_text(encoding="utf-8")))
        if isinstance(n, ast.Import | ast.ImportFrom)
    ]
