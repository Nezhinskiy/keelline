from __future__ import annotations

from pathlib import Path

from keelline.guards.audit import SHAPES, import_roots, run_self_test, scan_file, suite_files

ROOTS = frozenset({"widget"})

# A test that names `boot_demo`, imports it, and rebuilds the call `boot_demo` makes
# internally instead of calling it. The shape shipped once as a real defect.
_RE_DERIVES_INSTEAD_OF_INVOKING = """
from widget.boot import boot_demo
from widget.fixtures import build_fixtures


def test_boot_demo_builds_fixtures_in_resolved_locale() -> None:
    data = build_fixtures("2026-08-13", "en")
    assert data["language"] == "en"
"""

_ASSERTS_ON_THE_STUB = """
from unittest.mock import MagicMock


def test_stub_returns_configured_value() -> None:
    client = MagicMock()
    client.fetch.return_value = {"ok": True}
    assert client.fetch() == {"ok": True}
"""

_EXERCISES_THE_SUBJECT = """
from unittest.mock import MagicMock

from widget.boot import boot_demo


def test_boot_demo_builds_fixtures_in_resolved_locale() -> None:
    builder = MagicMock()
    boot_demo(builder=builder)
    builder.assert_called_once_with("2026-08-13", "en")
"""


def _scan(tmp_path: Path, source: str) -> list[str]:
    target = tmp_path / "test_sample.py"
    target.write_text(source, encoding="utf-8")
    return [f"{f.shape}:{f.detail}" for f in scan_file(target, SHAPES, ROOTS)]


def test_flags_a_test_that_names_an_entry_point_it_never_invokes(tmp_path: Path) -> None:
    findings = _scan(tmp_path, _RE_DERIVES_INSTEAD_OF_INVOKING)
    assert any(f.startswith("names-but-never-invokes") for f in findings), findings
    assert any("boot_demo" in f for f in findings), findings


def test_flags_an_assertion_on_the_stubs_own_return_value(tmp_path: Path) -> None:
    # The second shape, which nothing else in this file holds to a test-owned answer:
    # reddened by mutating `scan_file`'s `if "assert-on-double" in shapes:` to `if False:`.
    # Measured: it also reddens `test_self_test_proves_the_scanner_still_discriminates` and
    # the CLI test, because the module's known-bad corpus carries this shape too and the
    # command refuses on a self-test problem. That is the oracle chain working, not collateral
    # from an unrelated area -- but this is the assertion that says *which* shape was lost.
    findings = _scan(tmp_path, _ASSERTS_ON_THE_STUB)
    assert any(f.startswith("assert-on-double") for f in findings), findings


def test_clears_a_test_that_invokes_the_subject_and_asserts_its_effect(tmp_path: Path) -> None:
    # The negative half: a scanner that flags everything discriminates no better than one that
    # flags nothing. Reddened by mutating `_scan_names_but_never_invokes`'s
    # `if any(symbol in reached for symbol in named):` to `if False:`, which drops the check
    # that an invoked symbol clears the test. Measured -- and it also reddens
    # `test_self_test_proves_the_scanner_still_discriminates` and, through the command's
    # refusal on a self-test problem, the CLI test, because the module's own known-good corpus
    # holds this same shape. That is the oracle chain working, not collateral from an
    # unrelated area.
    assert _scan(tmp_path, _EXERCISES_THE_SUBJECT) == []


def test_an_import_alone_does_not_count_as_invoking_the_entry_point(tmp_path: Path) -> None:
    """The bug that silently zeroed the scanner's first draft: counting the identifier inside
    `from widget.boot import boot_demo` as a reference marks every imported symbol exercised,
    and a scanner that cannot go red is not evidence.

    This scans the same fixture as the first test in this file with a strictly weaker
    assertion, and the pair is deliberate. The first test pins *which* shape and *which*
    symbol, and it would still be red for the right reason if the scanner drifted; this one
    pins only that the scanner can go red at all on a corpus that must produce a finding --
    the single property whose loss is silent, and the one the first draft lost.
    """
    assert _scan(tmp_path, _RE_DERIVES_INSTEAD_OF_INVOKING) != []


def test_an_import_from_outside_the_roots_is_not_an_entry_point(tmp_path: Path) -> None:
    # `requests.get` in a test name is not a claim about code under test. This is the
    # assertion that the roots are configuration-derived rather than decoration: reddened by
    # mutating `_ModuleFacts`'s `if node.module.split(".")[0] in roots:` to `if True:`, which
    # makes every third-party import an entry point; measured, and it reddened this test alone.
    source = _RE_DERIVES_INSTEAD_OF_INVOKING.replace("widget.boot", "vendor.boot")
    assert not any(f.startswith("names-but-never-invokes") for f in _scan(tmp_path, source))


def test_self_test_proves_the_scanner_still_discriminates() -> None:
    # The expectation is read from the subject: the module grades its own corpora, so no edit
    # to those corpora can redden this. It pins that the command's own refusal path is quiet
    # on a healthy scanner; the two tests above hold the same shapes to a test-owned answer.
    assert run_self_test() == []


def test_import_roots_are_the_packages_and_modules_directly_under_each_root(tmp_path: Path) -> None:
    # A test module directly under a code root is not something the suite imports by name, and
    # counting it would make the suite its own subject. Reddened by mutating `import_roots`'s
    # `not child.name.startswith("test_")` to `not child.name.startswith("zzz_")`. Measured:
    # it also reddens the CLI test, whose fixture has a `test_*.py` directly under a code root
    # and asserts the derived names; no test outside this lane moved.
    src = tmp_path / "src"
    (src / "widget").mkdir(parents=True)
    (src / "widget" / "__init__.py").write_text("", encoding="utf-8")
    (src / "helper.py").write_text("", encoding="utf-8")
    (src / "test_not_code.py").write_text("", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    assert import_roots([src, scripts]) == frozenset({"widget", "helper", "scripts"})


def test_suite_files_are_every_test_module_under_the_roots(tmp_path: Path) -> None:
    # A suite that lays its tests out in subdirectories is the normal case, and a scanner that
    # silently walked only the top level would report a clean suite it never opened. Reddened
    # by mutating `suite_files`' `directory.rglob("test_*.py")` to `directory.glob(...)`;
    # measured, and it reddened this test alone.
    tests = tmp_path / "tests"
    (tests / "deep").mkdir(parents=True)
    (tests / "test_a.py").write_text("", encoding="utf-8")
    (tests / "deep" / "test_b.py").write_text("", encoding="utf-8")
    (tests / "conftest.py").write_text("", encoding="utf-8")
    assert suite_files([tests]) == [tests / "deep" / "test_b.py", tests / "test_a.py"]
