from __future__ import annotations

from pathlib import Path

import pytest

from keelline.guards import audit
from keelline.guards.audit import (
    SHAPES,
    import_roots,
    run_self_test,
    scan_file,
    scan_paths,
    suite_files,
)

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


# One test binds `sender` to a double; its sibling binds the same name to the real subject.
# Only the first asserts on a double.
_SIBLING_REUSES_A_DOUBLES_NAME = """
from unittest.mock import MagicMock

from widget.send import RealSender, RecordingSender


def test_recording_sender_keeps_what_it_was_given() -> None:
    sender = RecordingSender()
    assert sender.send("x") == "recorded"


def test_real_sender_receipt_carries_the_message_id() -> None:
    sender = RealSender(transport=MagicMock())
    receipt = sender.send("x")
    assert receipt.message_id == "1"
"""

_MODULE_LEVEL_DOUBLE = """
from widget.clock import FakeClock

CLOCK = FakeClock()


def test_first() -> None:
    assert CLOCK.now() == 5


def test_second() -> None:
    assert CLOCK.now() == 5
"""

# Still module scope: a global bound under a top-level compound statement is visible to every
# test, exactly like one bound at the top level.
_MODULE_LEVEL_DOUBLE_UNDER_COMPOUND_STATEMENTS = """
import sys

from widget.clock import FakeClock

try:
    CLOCK = FakeClock()
except ImportError:
    CLOCK = None

if sys.platform:
    TIMER = FakeClock()


def test_clock() -> None:
    assert CLOCK.now() == 5


def test_timer() -> None:
    assert TIMER.now() == 5
"""


def _scan(tmp_path: Path, source: str) -> list[str]:
    target = tmp_path / "test_sample.py"
    target.write_text(source, encoding="utf-8")
    return [f"{f.shape}:{f.detail}" for f in scan_file(target, SHAPES, ROOTS)]


def _tests_flagged_as_asserting_on_a_double(tmp_path: Path, source: str) -> set[str]:
    target = tmp_path / "test_sample.py"
    target.write_text(source, encoding="utf-8")
    return {f.test for f in scan_file(target, ("assert-on-double",), ROOTS)}


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


def test_a_double_bound_in_one_test_does_not_leak_into_its_siblings(tmp_path: Path) -> None:
    """A name bound to a double inside one test is that test's local, and nothing more.

    Module-level doubles used to be collected by walking the whole file, so the first test's
    `sender = RecordingSender()` made `sender` a double in every test of the file, and the
    second test's assertion on its real subject's receipt read as one on a double's return. On
    the suite this scanner was extracted from, that was 18 of 28 `assert-on-double` candidates.
    """
    # Mutation (declared): the module-scope walk widened back to `ast.walk(tree)`. It also
    # reddens the self-test, whose known-good corpus carries this shape.
    flagged = _tests_flagged_as_asserting_on_a_double(tmp_path, _SIBLING_REUSES_A_DOUBLES_NAME)
    assert flagged == {"test_recording_sender_keeps_what_it_was_given"}


def test_a_module_level_double_is_a_double_in_every_test(tmp_path: Path) -> None:
    # Mutation (declared): module-level collection removed. It also reddens the self-test,
    # whose known-bad corpus asserts on a module-level double.
    flagged = _tests_flagged_as_asserting_on_a_double(tmp_path, _MODULE_LEVEL_DOUBLE)
    assert flagged == {"test_first", "test_second"}


def test_a_double_bound_under_a_top_level_compound_statement_is_module_level(
    tmp_path: Path,
) -> None:
    # Narrowing the collection to the top-level statements alone would have been the obvious
    # fix for the leak, and it silently drops these. Mutation (declared): the walk reduced to
    # `tree.body`; it reddens this test alone.
    flagged = _tests_flagged_as_asserting_on_a_double(
        tmp_path, _MODULE_LEVEL_DOUBLE_UNDER_COMPOUND_STATEMENTS
    )
    assert flagged == {"test_clock", "test_timer"}


def test_self_test_proves_the_scanner_still_discriminates() -> None:
    # The expectation is read from the subject: the module grades its own corpora against its
    # own `_KNOWN_BAD_EXPECTED`, so an edit to both together cannot redden this. It pins that
    # the command's own refusal path is quiet on a healthy scanner; the tests above hold the
    # same shapes to a test-owned answer.
    assert run_self_test() == []


def test_the_self_test_refuses_a_shape_its_known_bad_sample_is_not_expected_to_produce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The per-test expectations only prove the shapes they name. A shape added to `SHAPES`
    # without a known-bad test would be graded by nothing, and the self-test would pass.
    # Mutation (declared): that problem never appended.
    kept = frozenset(
        entry for entry in audit._KNOWN_BAD_EXPECTED if entry[1] != "names-but-never-invokes"
    )
    monkeypatch.setattr(audit, "_KNOWN_BAD_EXPECTED", kept)
    problem = "no known-bad sample is expected to produce 'names-but-never-invokes'"
    assert problem in run_self_test()


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


def test_a_dangling_test_symlink_is_skipped_rather_than_aborting_the_scan(tmp_path: Path) -> None:
    """A `test_*.py` symlink whose target is gone -- routine after a bad merge -- is listed by
    `suite_files` (`rglob` matches on the name, without following the link) and then cannot be
    read. Measured before `scan_file` caught `OSError`: `FileNotFoundError` escaped the scan
    and the command exited `2`, the code this CLI reserves for "could not answer" and tells
    callers never to read as permission -- on a command that exits `0` by design.

    Oracle: `mutations.toml`, "an unreadable test file aborts the scan".

    The real file beside it is what keeps the assertion from passing vacuously: the scan has
    to get PAST the broken link and still report the finding the other file carries.
    """
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_real.py").write_text(_RE_DERIVES_INSTEAD_OF_INVOKING, encoding="utf-8")
    (tests / "test_dangling.py").symlink_to(tests / "gone.py")

    found = suite_files([tests])
    assert found == [tests / "test_dangling.py", tests / "test_real.py"]
    assert [f.shape for f in scan_paths(found, SHAPES, ROOTS)] == ["names-but-never-invokes"]


def test_a_code_root_that_cannot_be_read_yields_no_import_names(tmp_path: Path) -> None:
    """The same direction on the other walk. `import_roots` reads each root the containment
    check returned, and the tree can change between the two calls -- a checkout, a `rm -rf`, a
    directory whose mode a repository's own setup narrowed. Measured before the catch:
    `PermissionError` out of `Path.is_file()`, which swallows a MISSING path but re-raises a
    forbidden one, so guarding `iterdir` alone was not enough.

    Reddened by narrowing `import_roots`' `except OSError` to `except ValueError`, which
    nothing on that path raises; measured.

    Not in `mutations.toml`, deliberately: the skip below makes this test environment-
    dependent -- a run as root reads a `0o000` directory regardless -- and a declared mutation
    whose named test can SKIP reports "caught" while proving nothing, which is the vacuity the
    oracle exists to rule out.
    """
    readable = tmp_path / "src"
    readable.mkdir()
    (readable / "helper.py").write_text("", encoding="utf-8")
    forbidden = tmp_path / "vendor"
    forbidden.mkdir(mode=0o000)
    try:
        try:
            list(forbidden.iterdir())
        except OSError:
            pass
        else:
            pytest.skip("this run can read a 0o000 directory; the fault cannot be staged")
        # The readable root is scanned anyway: the refusal is per root, not per command.
        assert import_roots([readable, forbidden]) == frozenset({"helper"})
    finally:
        forbidden.chmod(0o700)
