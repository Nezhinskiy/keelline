"""The release area's `api.py` is held to the same contract every other area's is.

CONTRIBUTING states it once for all of them: "`api.py` is the area's import surface. Other
areas import from it and from nothing else, and its `__all__` must equal exactly what it
imports — a test parses the file and checks."
"""

from __future__ import annotations

import keelline.release.api as release


def test_the_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # An equality and not a subset, for the reason tests/doctor/test_surface.py gives: a subset
    # lets an export arrive unnoticed. `doctor` is the one consumer today and it reads all but
    # `drift`, which `tests/test_manifests.py` reads — `write_record` is deliberately absent,
    # because writing the record is this area's own business and no other lane's.
    required = {
        # what the record covers, and where it lives: `doctor` names the file it compared.
        "HASHED_FILES",
        "RECORD",
        # the three answers about a record: what is there, what was recorded, what differs.
        "digests",
        "read_record",
        "drift",
        # "present and not a record" is a distinct answer from "absent" — absent skips in
        # `doctor` and unreadable must be red — so the consumer needs the class to branch on.
        "UnreadableRecord",
    }
    assert required == set(release.__all__)


def test_the_export_list_is_exactly_what_the_module_imports_from_this_lane() -> None:
    import ast
    from pathlib import Path

    imported: set[str] = set()
    tree = ast.parse(Path(release.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Import), "the surface re-exports, it does not import"
        if not isinstance(node, ast.ImportFrom) or node.module == "__future__":
            continue
        assert node.module is not None and node.module.startswith("keelline.release.")
        imported |= {alias.asname or alias.name for alias in node.names}
    assert imported == set(release.__all__)
    for name in release.__all__:
        assert hasattr(release, name)


def test_every_type_the_surface_names_in_a_signature_is_on_the_surface() -> None:
    # Derived rather than restated, exactly as `tests/doctor/test_surface.py` derives it: the
    # two tests above cannot catch a name nobody added to either side, because one is a list a
    # person maintains and the other compares the module against itself.
    import dataclasses
    import inspect
    import typing

    def area_types(annotation: object) -> set[str]:
        found: set[str] = set()
        if isinstance(annotation, type) and annotation.__module__.startswith("keelline.release"):
            found.add(annotation.__name__)
        for argument in typing.get_args(annotation):
            found |= area_types(argument)
        return found

    exported = set(release.__all__)
    missing: dict[str, set[str]] = {}
    examined: list[str] = []
    for name in sorted(exported):
        thing = getattr(release, name)
        is_record = isinstance(thing, type) and dataclasses.is_dataclass(thing)
        if not (inspect.isfunction(thing) or is_record):
            continue
        examined.append(name)
        named: set[str] = set()
        for hint in typing.get_type_hints(thing).values():
            named |= area_types(hint)
        if named - exported:
            missing[name] = named - exported
    # The walk is asserted non-empty before anything is asserted about it: a surface whose
    # callables all stopped being callables would otherwise leave `missing` empty and this test
    # green while checking nothing.
    assert examined, "the surface exports no function or record, so this checked nothing"
    assert not missing, f"named by the surface and absent from it: {missing}"


def test_the_surface_is_a_module_not_the_package_init() -> None:
    # Measured on this project's other areas: with the list in `__init__.py`, the hook registry
    # pulls the whole area — configuration included — into every `discover()` call.
    import ast
    from pathlib import Path

    import keelline.release

    init = Path(next(iter(keelline.release.__path__))) / "__init__.py"
    tree = ast.parse(init.read_text(encoding="utf-8"))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom)]
