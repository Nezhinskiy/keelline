# tests/guards/test_surface.py
from __future__ import annotations

import keelline.guards.api as guards


def test_the_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # This list is the contract. A lane that needs something absent from it grows the list
    # deliberately, in a commit that says which lane and why — and an EQUALITY is what makes
    # that true. `required <= set(__all__)` let an export be added and pass, and so did the
    # second test below, which compares `__all__` against this module's own imports: adding an
    # import and an `__all__` entry together satisfied both, so between them the two tests
    # could only catch a REMOVED export. Nothing an area publishes should arrive unnoticed;
    # growing this set in the same commit is the whole cost.
    #
    # No `mutations.toml` entry: the mutation is adding an export, which is two lines in
    # `api.py` (the import and the `__all__` entry) and not one substituted line. Measured by
    # hand instead — re-exporting `hygiene.is_pytest_run` reddens this test and this test alone,
    # and under the old `required <= set(...)` the very same change left all three tests green.
    required = {
        # the scanner, for any later guard
        "Heredoc",
        "tokenize",
        "segments",
        "operator_pieces",
        "command_words",
        # the judge, for hooks-core's smoke assertions
        "ALLOW",
        "Verdict",
        "judge",
        "LEAK_REASON",
        "SLEEP_REASON",
        "RESTORE_HINT",
        # the commit rules, for assess and workflows
        "ATTRIBUTION_LABELS",
        "Offence",
        "Report",
        "Violation",
        "check_range",
        "offending_lines",
        "strip_message",
        # the git hook, for setup
        "HOOK_NAME",
        "HOOK_MARKER",
        "Installed",
        "Removed",
        "hooks_dir",
        "install",
        "uninstall",
        # hygiene and the audit, for assess
        "Hygiene",
        "inspect",
        "red_exit",
        "Finding",
        "SHAPES",
        "import_roots",
        "scan_paths",
        "suite_files",
        "contained_roots",
        # the failure attribution, for the skill that wraps it and for assess
        "attribute",
        "Attribution",
        "VERDICTS",
    }
    assert required == set(guards.__all__)


def test_the_export_list_is_exactly_what_the_module_imports_from_this_lane() -> None:
    import ast
    from pathlib import Path

    imported: set[str] = set()
    tree = ast.parse(Path(guards.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Import), "the surface re-exports, it does not import"
        if not isinstance(node, ast.ImportFrom) or node.module == "__future__":
            continue
        assert node.module is not None and node.module.startswith("keelline.guards.")
        imported |= {alias.asname or alias.name for alias in node.names}
    assert imported == set(guards.__all__)
    for name in guards.__all__:
        assert hasattr(guards, name)


def test_the_surface_is_a_module_not_the_package_init() -> None:
    import ast
    from pathlib import Path

    import keelline.guards

    init = Path(next(iter(keelline.guards.__path__))) / "__init__.py"
    tree = ast.parse(init.read_text(encoding="utf-8"))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom)]
