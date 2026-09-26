"""Audit pytest files for assertions that do not exercise the code under test.

Encodes the two shapes rejected by the rule "a test must exercise the code under test":

* ``assert-on-double`` -- the asserted value is produced by *invoking* a test double,
  so production code cannot influence whether the test passes.
* ``names-but-never-invokes`` -- the test's own name states an entry point that the
  test imports but never calls. The wiring stays uncovered and a regression in it
  passes. This is the shape that shipped as a real defect: a test that sat under a
  ``describe`` block naming the entry point and rebuilt the call the entry point
  makes internally, instead of calling the entry point.

  WHAT THE PREDICATE ACTUALLY ASKS is "never MENTIONS again", not "never calls":
  `_referenced_names` adds every `Name.id` and `Attribute.attr` it walks, whether or
  not it is a call target. Both directions of the gap were measured. The textbook
  instance is cleared by a bare mention -- `assert boot_demo is not None` satisfies the
  predicate while calling nothing -- and a `conftest.py` fixture that DOES call the
  entry point is still flagged, because the call lives outside the test function this
  walks. On this repository's own suite the shape reports six candidates and all six
  are name collisions between a test's name and an imported symbol.

  Left as it is, deliberately, and the documentation corrected to match (`docs/cli.md`).
  The audit exits 0 by design -- it is a triage list, not a gate -- so the gap costs a
  reader a moment per candidate, while narrowing the predicate to call targets changes
  what a ported scanner reports with none of its source corpus available to re-grade it
  against. Restricting it to call targets, and reaching into the fixtures a test
  requests, are the open options for the lane that turns this into a gate --
  `keelline assess` leaves it out of its inventory until its candidates are triaged --
  where a tightened predicate can be graded before anything is blocked on it.

This is an **audit tool, not yet a gate**. `test audit-entrypoints` exits 0 whether or not
it finds candidates: a name collision between a test's name and an imported symbol is a
candidate for a person to read, not a build failure, and a suite that has never been triaged
reports several of them on its first run. A blocking guard needs that triage to zero first.

`run_self_test` runs the scanner against known-bad and known-good samples and returns the
problems it found, empty when the scanner still discriminates. A scanner that reports nothing
is indistinguishable from a broken scanner, so that check is this module's own oracle: the
first working draft of the JavaScript twin silently returned zero findings because it counted
``import { bootDemo }`` as a call. The command refuses rather than reporting a clean suite
when this list is non-empty.

The roots are not hard-coded. `import_roots` derives the package and module names that count
as "the code under test" from the directories `ledger.code_roots` names, so a repository that
lays its source out differently is scanned against its own layout.
"""

from __future__ import annotations

import ast
import re
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# Constructors and helpers whose result stands in for a dependency.
DOUBLE_CTORS = frozenset({"Mock", "MagicMock", "AsyncMock", "NonCallableMock", "PropertyMock"})
FAKE_CLASS_PREFIXES = ("Fake", "Stub", "Dummy", "Spy", "Recording", "Scripted")
DOUBLE_PARAM_PREFIXES = ("mock_", "stub_", "fake_", "dummy_")
DOUBLE_PARAM_SUFFIXES = ("_mock", "_stub", "_fake")

# Attributes that INSPECT a double's recorded interactions rather than run its stubbed
# behaviour. Asserting on these is the legitimate way to check the subject's effects.
INSPECT_ATTRS = frozenset(
    {
        "call_args",
        "call_args_list",
        "call_count",
        "called",
        "mock_calls",
        "method_calls",
        "await_args",
        "await_args_list",
        "await_count",
        "awaited",
        "return_value",
        "side_effect",
        "spec",
    }
)

SHAPES = ("assert-on-double", "names-but-never-invokes")

# How much of an unparsed expression a finding's `detail` carries. It is read in a terminal
# beside a path, a line number and a test name; a longer slice wraps and buries the finding
# it is there to identify. Not a configuration key: it bounds a diagnostic string, not a
# decision, and no repository needs a different answer to fit its own code on a line.
_DETAIL_CHARS = 100

# How many of a symbol's tokens a test's name must state before the name is read as a claim
# about that symbol. One token (`run`, `boot`, `main`) collides with half a suite's test names
# and would make every finding noise. Not a configuration key: lowering it destroys the
# shape's precision and raising it silences the shape, and neither is a per-repository choice
# -- it is the threshold this scanner's own known-good corpus is graded against.
_MIN_SYMBOL_TOKENS = 2


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    test: str
    shape: str
    detail: str

    def render(self) -> str:
        return f"{self.path}:{self.line}\t{self.test}\t{self.shape}\t{self.detail}"


def _tokens(name: str) -> list[str]:
    """``buildFixtures`` -> ``[build, fixtures]``; ``apply_effects`` -> ``[apply, effects]``."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return [part for part in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if part]


def _contains_subsequence(haystack: list[str], needle: list[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    span = len(needle)
    return any(haystack[i : i + span] == needle for i in range(len(haystack) - span + 1))


def _root_name(node: ast.expr) -> str | None:
    current: ast.expr = node
    while isinstance(current, ast.Attribute | ast.Subscript | ast.Await | ast.Starred):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def _attribute_chain(node: ast.expr) -> list[str]:
    chain: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        chain.append(current.attr)
        current = current.value
    return list(reversed(chain))


def _is_double_constructor(func: ast.expr, fake_classes: frozenset[str]) -> bool:
    if isinstance(func, ast.Name):
        return (
            func.id in DOUBLE_CTORS
            or func.id == "patch"
            or func.id in fake_classes
            or func.id.startswith(FAKE_CLASS_PREFIXES)
        )
    if isinstance(func, ast.Attribute):
        if func.attr in DOUBLE_CTORS:
            return True
        # Only unittest.mock's patch -- never a TestClient's HTTP `client.patch(...)`.
        owner = func.value
        owner_name = owner.id if isinstance(owner, ast.Name) else None
        return func.attr in {"patch", "object"} and owner_name in {
            "mock",
            "patch",
            "mocker",
            "unittest",
        }
    return False


class _ModuleFacts:
    """Per-file context: what is imported from the code roots, and what is a double."""

    def __init__(self, tree: ast.Module, roots: frozenset[str]) -> None:
        self.root_symbols: set[str] = set()
        fake_classes: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in roots:
                    self.root_symbols.update(a.asname or a.name for a in node.names)
            elif isinstance(node, ast.ClassDef) and node.name.startswith(FAKE_CLASS_PREFIXES):
                fake_classes.add(node.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name.startswith(FAKE_CLASS_PREFIXES):
                        fake_classes.add(name)
        self.fake_classes = frozenset(fake_classes)

        self.module_doubles: set[str] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and _is_double_constructor(node.value.func, self.fake_classes)
            ):
                self.module_doubles.update(t.id for t in node.targets if isinstance(t, ast.Name))

        self.local_defs: dict[str, ast.AST] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                self.local_defs.setdefault(node.name, node)


def _referenced_names(node: ast.AST) -> set[str]:
    """Every name the body calls or references, including attribute tails."""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
        elif isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def _reachable_names(node: ast.AST, facts: _ModuleFacts) -> set[str]:
    """Names reachable from a test, following local helpers transitively."""
    reached = _referenced_names(node)
    seen: set[str] = set()
    frontier = set(reached)
    while frontier:
        nxt: set[str] = set()
        for name in frontier:
            if name in seen or name not in facts.local_defs:
                continue
            seen.add(name)
            more = _referenced_names(facts.local_defs[name])
            nxt |= more - reached
            reached |= more
        frontier = nxt
    return reached


class _DoubleAssertVisitor(ast.NodeVisitor):
    """Flags asserts whose value is produced by invoking a double."""

    def __init__(self, doubles: set[str], facts: _ModuleFacts) -> None:
        self.doubles = set(doubles)
        self.facts = facts
        self.tainted: set[str] = set()
        self.hits: list[tuple[int, str]] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        value = node.value.value if isinstance(node.value, ast.Await) else node.value
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if isinstance(value, ast.Call):
            if _is_double_constructor(value.func, self.facts.fake_classes):
                self.doubles.update(targets)
            elif self._invokes_double(value):
                self.tainted.update(targets)
        elif isinstance(value, ast.Attribute | ast.Name) and _root_name(value) in self.doubles:
            self.doubles.update(targets)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            ctx = item.context_expr
            if (
                isinstance(ctx, ast.Call)
                and isinstance(item.optional_vars, ast.Name)
                and _is_double_constructor(ctx.func, self.facts.fake_classes)
            ):
                self.doubles.add(item.optional_vars.id)
        self.generic_visit(node)

    visit_AsyncWith = visit_With  # type: ignore[assignment]

    def _invokes_double(self, node: ast.AST) -> bool:
        target = node.value if isinstance(node, ast.Await) else node
        if not isinstance(target, ast.Call):
            return False
        if _root_name(target.func) not in self.doubles:
            return False
        chain = _attribute_chain(target.func)
        # Inspecting a double's recorded calls is the legitimate shape, not an invocation.
        return not (chain and (chain[-1].startswith("assert_") or chain[-1] in INSPECT_ATTRS))

    def visit_Assert(self, node: ast.Assert) -> None:
        for sub in ast.walk(node.test):
            if self._invokes_double(sub):
                self.hits.append((node.lineno, ast.unparse(sub)[:_DETAIL_CHARS]))
                break
            if isinstance(sub, ast.Name) and sub.id in self.tainted:
                self.hits.append((node.lineno, f"value derived from double: {sub.id}"))
                break
        self.generic_visit(node)


def _scan_assert_on_double(path: Path, tree: ast.Module, facts: _ModuleFacts) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue
        params = {a.arg for a in node.args.args + node.args.kwonlyargs}
        doubles = set(facts.module_doubles) | {
            p
            for p in params
            if p.startswith(DOUBLE_PARAM_PREFIXES) or p.endswith(DOUBLE_PARAM_SUFFIXES)
        }
        visitor = _DoubleAssertVisitor(doubles, facts)
        for stmt in node.body:
            visitor.visit(stmt)
        findings.extend(
            Finding(str(path), line, node.name, "assert-on-double", detail)
            for line, detail in visitor.hits
        )
    return findings


def _scan_names_but_never_invokes(
    path: Path, tree: ast.Module, facts: _ModuleFacts
) -> list[Finding]:
    if not facts.root_symbols:
        return []
    symbol_tokens = {s: _tokens(s) for s in facts.root_symbols}
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue
        name_tokens = _tokens(node.name)
        # Single-token symbols match far too loosely to carry a claim.
        named = [
            symbol
            for symbol, toks in symbol_tokens.items()
            if len(toks) >= _MIN_SYMBOL_TOKENS and _contains_subsequence(name_tokens, toks)
        ]
        if not named:
            continue
        reached = _reachable_names(node, facts)
        # If ANY symbol the name states is invoked, the entry point is covered; the rest
        # are partial-name collisions (`build_fixtures` inside `build_fixtures_async`).
        if any(symbol in reached for symbol in named):
            continue
        findings.append(
            Finding(
                str(path),
                node.lineno,
                node.name,
                "names-but-never-invokes",
                ",".join(sorted(named)),
            )
        )
    return findings


def import_roots(roots: Iterable[Path]) -> frozenset[str]:
    """The top-level import names the code roots publish, which is what a test can import.

    Replaces the source tool's hard-coded root tuple: for each directory, its own name when it
    is a package, plus the name of every package directly under it and the stem of every `.py`
    directly under it other than `__init__.py` and a `test_*.py`.
    """
    names: set[str] = set()
    for directory in roots:
        # The WHOLE per-root read is guarded, not `iterdir` alone: `Path.is_file()` swallows a
        # missing path but re-raises `PermissionError`, so the `__init__.py` probe one line
        # down is the first thing an unreadable root raises from -- measured. A root that
        # cannot be read -- unreadable, or gone since `contained_roots` judged it -- then
        # contributes no import names instead of aborting the command with `internal error:
        # PermissionError` and exit 2. Exit 2 is the code this CLI reserves for "could not
        # answer"; callers are told never to read it as permission, so raising an undocumented
        # one out of an advisory scan is the wrong failure. Under-reporting is the direction
        # this module already chose for a file it cannot parse, and it is the same choice here.
        try:
            if (directory / "__init__.py").is_file():
                names.add(directory.name)
            # Materialised inside the `try`: `iterdir` is a generator, so the error it raises
            # for an unreadable directory arrives on the first step, not on the call.
            children = list(directory.iterdir())
            for child in children:
                if child.is_dir() and (child / "__init__.py").is_file():
                    names.add(child.name)
                elif (
                    child.suffix == ".py"
                    and child.name != "__init__.py"
                    and not child.name.startswith("test_")
                ):
                    names.add(child.stem)
        except OSError:
            continue
    return frozenset(names)


def suite_files(roots: Iterable[Path]) -> list[Path]:
    """Every `test_*.py` under the roots, sorted."""
    return sorted(path for directory in roots for path in directory.rglob("test_*.py"))


def scan_file(path: Path, shapes: tuple[str, ...], roots: frozenset[str]) -> list[Finding]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        # `OSError` covers the file that `suite_files` listed and this cannot read: a DANGLING
        # SYMLINK is the routine one -- `rglob` yields the link by name, `read_text` then
        # raises `FileNotFoundError` -- and it is what a bad merge leaves behind. Measured
        # before this was caught: the whole scan aborted with `internal error:
        # FileNotFoundError` and exit 2, the code callers are told never to read as
        # permission. Skipping the file under-reports, which is the direction the two parse
        # errors beside it already chose.
        return []
    facts = _ModuleFacts(tree, roots)
    findings: list[Finding] = []
    if "assert-on-double" in shapes:
        findings.extend(_scan_assert_on_double(path, tree, facts))
    if "names-but-never-invokes" in shapes:
        findings.extend(_scan_names_but_never_invokes(path, tree, facts))
    return findings


def scan_paths(
    paths: Iterable[Path], shapes: tuple[str, ...], roots: frozenset[str]
) -> list[Finding]:
    """Scan files. Unlike the source tool this never walks a directory: `suite_files` owns the
    walk, so the caller can report how many files were scanned and the two halves cannot
    disagree about which files those were."""
    findings: list[Finding] = []
    for path in paths:
        findings.extend(scan_file(path, shapes, roots))
    return findings


_KNOWN_BAD = '''
from unittest.mock import MagicMock

from widget.boot import boot_demo
from widget.fixtures import build_fixtures


def test_boot_demo_builds_fixtures_in_resolved_locale() -> None:
    """Re-derives what boot_demo does internally; never calls boot_demo."""
    data = build_fixtures("2026-08-13", "en")
    assert data["language"] == "en"


def test_stub_returns_configured_value() -> None:
    """Asserts on the double's own configured behaviour."""
    client = MagicMock()
    client.fetch.return_value = {"ok": True}
    assert client.fetch() == {"ok": True}
'''

_KNOWN_GOOD = '''
from unittest.mock import MagicMock

from widget.boot import boot_demo
from widget.fixtures import build_fixtures


def test_boot_demo_builds_fixtures_in_resolved_locale() -> None:
    """Invokes the entry point and asserts what it passed to its collaborator."""
    builder = MagicMock(wraps=build_fixtures)
    boot_demo(builder=builder)
    builder.assert_called_once_with("2026-08-13", "en")


def test_client_receipt_carries_the_transport_response() -> None:
    """Stubs the dependency, exercises the subject, asserts on the subject."""
    client = MagicMock()
    client.fetch.return_value = {"ok": True}
    assert boot_demo(client=client) == "booted"
'''

# The corpora above import from `widget.boot` and `widget.fixtures`, so the self-test grades
# the scanner with exactly this root set. It is the module's own fixture, not a repository's
# configuration, which is why it is a constant here and not a parameter.
_SELF_TEST_ROOTS = frozenset({"widget"})


def run_self_test() -> list[str]:
    """Prove the scanner discriminates: red on known-bad, green on known-good.

    Returns the problems found; an empty list means the scanner still discriminates. The
    caller decides what a problem costs -- the command refuses, because a scanner that cannot
    go red is not evidence about the suite it just reported clean.
    """
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "test_known_bad.py"
        good = Path(tmp) / "test_known_good.py"
        bad.write_text(_KNOWN_BAD, encoding="utf-8")
        good.write_text(_KNOWN_GOOD, encoding="utf-8")

        bad_shapes = {f.shape for f in scan_file(bad, SHAPES, _SELF_TEST_ROOTS)}
        for shape in SHAPES:
            if shape not in bad_shapes:
                problems.append(f"known-bad sample was NOT flagged for {shape!r}")

        for finding in scan_file(good, SHAPES, _SELF_TEST_ROOTS):
            problems.append(f"known-good sample was flagged: {finding.render()}")
    return problems
