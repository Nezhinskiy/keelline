"""`README.md`'s "What stayfixed sends where", held to the code.

The section declares every program stayfixed starts that can reach a network, and every file its
templates write under `.github/`, which GitHub runs. This module holds it to both, in both
directions: a launch with no row is an undisclosed destination, which the plugin directory's
security scan rejects, and a row with no launch is a promise about nothing.

The launches are found by walking the package's syntax from the seams every process start goes
through — `subprocess` and the other standard-library starters, the `Runner` seam, `git_run` and the
helpers that forward to it — and not from argv shapes, so a launch of a shape the walk does not
recognise is a finding until someone reads it. What a static walk cannot see is dynamic dispatch:
a launcher reached through `getattr`, `importlib` or a name built at run time.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SRC = ROOT / "src" / "stayfixed"
TEMPLATES = SRC / "templates"
# Every standard-library module that gives a process a connection of its own. A listed module
# matches with everything below it (`asyncio.streams` is `asyncio`'s), and never by its root alone:
# `urllib`, `http` and `logging` are not listed, because `urllib.parse`, `http.HTTPStatus` and a
# plain logger reach nothing, while `urllib.request`, `http.client`, `logging.handlers` and
# `logging.config` (whose `listen()` opens a socket) do. `asyncio` is listed whole although most of
# it reaches nothing: its connection calls and its subprocess calls come in through one import,
# which a match on names cannot tell apart, and the package imports it for neither. A module that
# wants it for a subprocess is an edit here that says so, and the launches it makes are walked
# below like any other. `smtpd`, `asyncore` and `asynchat` are gone from 3.12 and importable on the
# 3.11 floor; `_socket` and `_ssl` are what `socket` and `ssl` are built on.
NETWORK_MODULES = frozenset(
    {
        "_socket",
        "_ssl",
        "asynchat",
        "asyncio",
        "asyncore",
        "ftplib",
        "http.client",
        "http.server",
        "imaplib",
        "logging.config",
        "logging.handlers",
        "multiprocessing.connection",
        "multiprocessing.managers",
        "nntplib",
        "poplib",
        "smtpd",
        "smtplib",
        "socket",
        "socketserver",
        "ssl",
        "telnetlib",
        "urllib.request",
        "urllib.robotparser",
        "webbrowser",
        "wsgiref.simple_server",
        "xmlrpc.client",
        "xmlrpc.server",
    }
)


@dataclass(frozen=True)
class Seam:
    """How a launch's argv arrives. `program` is what the seam itself puts first; the rest is the
    call's arguments from position `at` on when `spread`, or else the one list at `at`. A seam that
    does not `read` takes a shell string, or an argv in a form the walk does not follow."""

    program: tuple[str, ...] = ()
    at: int = 0
    spread: bool = False
    reads: bool = True


LAUNCH = Seam()
UNREAD = Seam(reads=False)
# Every standard-library function that starts a process, by `(module, function)`.
STDLIB_LAUNCHES: dict[tuple[str, str], Seam] = {
    ("subprocess", "run"): LAUNCH,
    ("subprocess", "Popen"): LAUNCH,
    ("subprocess", "call"): LAUNCH,
    ("subprocess", "check_call"): LAUNCH,
    ("subprocess", "check_output"): LAUNCH,
    ("pty", "spawn"): LAUNCH,
    ("asyncio", "create_subprocess_exec"): Seam(spread=True),
    ("asyncio", "create_subprocess_shell"): UNREAD,
}
# A call to any other `subprocess` name is a launch too — `getoutput` and `getstatusoutput` take a
# shell string — except these, which start nothing. So is a call to `os.system`, `os.popen`,
# `os.startfile` and the `exec`, `fexec`, `spawn` and `posix_spawn` families, and to an event loop's
# `subprocess_exec` and `subprocess_shell` on whatever loop a call holds. The walk reads none of
# their argvs, so each is a finding until `PASS_THROUGH` names it.
SUBPROCESS_INERT = frozenset(
    {
        "CalledProcessError",
        "CompletedProcess",
        "SubprocessError",
        "TimeoutExpired",
        "list2cmdline",
        "DEVNULL",
        "PIPE",
        "STDOUT",
    }
)
# The modules whose names are launchers: a star import of one binds names the walk cannot follow.
LAUNCHER_MODULES = frozenset({"os", "subprocess"} | {module for module, _ in STDLIB_LAUNCHES})
OS_LAUNCH_PREFIXES = ("system", "popen", "startfile", "exec", "fexec", "spawn", "posix_spawn")
LOOP_LAUNCHES = frozenset({"subprocess_exec", "subprocess_shell"})
# The package's functions that launch a process on their caller's behalf, by `(file, function)`. A
# call to one is a seam call, read at the caller. Inside one, a launch the walk cannot read is the
# seam handing its caller's arguments on, and is not a call site of its own; one it can read is
# classified like any other, so the exemption covers the forwarding and nothing the seam adds. A
# new helper that forwards its own arguments to a launch is a finding until it is listed here.
SEAMS: dict[tuple[str, str], Seam] = {
    ("src/stayfixed/gitenv.py", "git_run"): Seam(("git",), at=1, spread=True),
    ("src/stayfixed/memory/store.py", "_git"): Seam(("git",), at=1, spread=True),
    ("src/stayfixed/assess/probes.py", "_git"): Seam(("git",), at=1, spread=True),
    ("src/stayfixed/assess/rule.py", "_read"): Seam(("git",), at=1, spread=True),
    ("src/stayfixed/attach/exclude.py", "_unmatched"): Seam(("git",), at=2, spread=True),
    ("src/stayfixed/setup/run.py", "_ask"): Seam(("git",), at=1, spread=True),
    ("src/stayfixed/overlay/publish.py", "_git"): Seam(("git",), at=1),
    # The real `Runner`. Calls reach it as `<…runner>.run(argv, cwd)`, never by this name.
    ("src/stayfixed/runner.py", "_SubprocessRunner.run"): LAUNCH,
}
# git's global options that take their value as the next argument; the subcommand follows them.
GIT_VALUED_OPTIONS = ("-C", "-c")
# Options with which a git command that otherwise reads the local repository asks a remote instead
# (`git archive --remote=<url>`). Wherever one appears, the call is not local.
GIT_REMOTE_OPTIONS = ("--remote", "--upload-pack", "--receive-pack", "--exec")
# The rows of a launch that reaches nothing past this machine.
NO_ROWS: frozenset[str] = frozenset()
# Each launch whose argv the walk cannot read, by `(file, function)`, and the README rows it can
# reach. The comment says what it runs; a reviewer reads it, and a new such launch is a finding
# until it has an entry.
PASS_THROUGH: dict[tuple[str, str], frozenset[str]] = {
    # A project's own `[gates.custom.<name>] run`, launched as configured.
    ("src/stayfixed/assess/gates.py", "_custom.run"): frozenset({"[gates.custom]"}),
    # `claude plugin marketplace add`, `claude plugin install`, `codex plugin marketplace add` and
    # `codex plugin add`, each built by a lambda in `_MARKETPLACE_ADD` or `_PLUGIN_INSTALL`, which
    # `test_the_plugin_installs_reach_the_rows_their_entry_names` classifies.
    ("src/stayfixed/setup/run.py", "_install_plugins"): frozenset(
        {"claude plugin", "codex plugin"}
    ),
    # `towncrier build --version X --yes [--draft]`, assembled before the call: it renders
    # `changelog.d/` into `CHANGELOG.md`.
    ("src/stayfixed/release/notes.py", "build"): NO_ROWS,
    # `git [-c core.excludesFile=…] --git-dir=… --work-tree=<empty> check-ignore --no-index
    # --stdin -z`, assembled in `asked`: the owner's own exclude files, asked about.
    ("src/stayfixed/attach/exclude.py", "unhidden_by_owner"): NO_ROWS,
    # `hooks/run-hook.sh open --version` under the plugin root this process derived: stayfixed's
    # own hook wrapper, asked for its version.
    ("src/stayfixed/doctor/checks.py", "_wrapper"): NO_ROWS,
}
# Where each program a seam call runs can reach, by the argv prefix that decides it: the README
# row that declares it, by the row's first code span. `sh -c` runs the command `test attribute
# --command` names, which reaches wherever it reaches.
NETWORK: dict[tuple[str, ...], str] = {
    ("gh",): "gh",
    ("git", "clone"): "git clone",
    ("git", "fetch"): "git fetch",
    ("git", "push"): "git push",
    ("git", "pull"): "git pull",
    ("git", "ls-remote"): "git ls-remote",
    ("claude", "plugin"): "claude plugin",
    ("codex", "plugin"): "codex plugin",
    ("pre-commit", "install"): "pre-commit install",
    ("sh", "-c"): "sh -c",
}
# The programs a seam call runs that reach nothing past this machine, by argv prefix, each as
# narrow as the subcommand's other forms require: `git remote` and `git worktree` have forms that
# ask a remote or change one, so only the forms in use are listed. A call in neither table is a
# finding: it has to be read and put in one of the two.
LOCAL = frozenset(
    {
        ("git", "--version"),
        # The one valueless global option a call puts before the subcommand. Listed whole, so that
        # the option before any other subcommand is a finding and not a pass.
        ("git", "--literal-pathspecs", "ls-tree"),
        ("git", "add"),
        ("git", "archive"),
        ("git", "cat-file"),
        ("git", "check-ignore"),
        ("git", "commit"),
        ("git", "config"),
        ("git", "diff"),
        ("git", "grep"),
        ("git", "init"),
        ("git", "log"),
        ("git", "ls-files"),
        ("git", "ls-tree"),
        ("git", "merge-base"),
        ("git", "remote", "get-url"),
        ("git", "rev-list"),
        ("git", "rev-parse"),
        ("git", "show-ref"),
        ("git", "status"),
        ("git", "symbolic-ref"),
        ("git", "worktree", "list"),
        ("tar", "-xf"),
    }
)
# Local only as the whole argv: `git remote` alone lists the remotes' names, and anything after it
# is a form to read first.
LOCAL_WHOLE = frozenset({("git", "remote")})
# Vacuity floors, not coverage: 88 launches and 141 modules today.
SEAM_CALLS_FLOOR = 80
MODULES_FLOOR = 120
# The section, everything between its heading and the next `## ` heading, and a code span.
_SENDS_SECTION = re.compile(
    r"^## What stayfixed sends where\n(.*?)(?=^## )", re.MULTILINE | re.DOTALL
)
_CODE_SPAN = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class SeamCall:
    """One place the package starts a process, and what the walk read of its argv: an element's
    string, or `None` where it could not read one. `argv` is `None` when the walk could not read as
    far as what decides the program (git's subcommand); `whole` is false when the reading ended at
    a spread of unknown length."""

    file: str
    line: int
    function: str
    argv: tuple[str | None, ...] | None
    whole: bool


@dataclass(frozen=True)
class Bindings:
    """What the names in one file are bound to: `functions` maps a bare name to the package
    function it calls, as `(file, function)`; `stdlib` maps one imported by name from the standard
    library to `(module, function)`; `modules` maps a name, dotted or not, to the module it is."""

    functions: dict[str, tuple[str, str]]
    stdlib: dict[str, tuple[str, str]]
    modules: dict[str, str]


def _package_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _modules(tree: ast.Module) -> set[str]:
    """Every module `tree` imports, by dotted name: `import a.b` and `from a import b` both name
    `a.b`, because the second can import a submodule and the syntax cannot say which. Relative
    imports are left out: they name the package's own modules, never the standard library's."""
    named: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            named.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            named.add(node.module)
            named.update(f"{node.module}.{alias.name}" for alias in node.names)
    return named


def network_imports(root: Path) -> list[tuple[str, str]]:
    """`(file, module)` for each network module a file under `root` imports."""
    return [
        (path.relative_to(ROOT).as_posix(), module)
        for path in _package_files(root)
        for module in sorted(_modules(ast.parse(path.read_text(encoding="utf-8"))))
        if _reaches_a_network(module)
    ]


def _reaches_a_network(module: str) -> bool:
    return any(module == listed or module.startswith(f"{listed}.") for listed in NETWORK_MODULES)


def _strings(node: ast.expr | None) -> list[str] | None:
    """The strings of a tuple or list made only of string literals."""
    if not isinstance(node, (ast.Tuple, ast.List)):
        return None
    strings = []
    for element in node.elts:
        if not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
            return None
        strings.append(element.value)
    return strings


def _constants(tree: ast.Module) -> dict[str, str | list[str]]:
    """Module-level names bound to a string, or to a tuple or list of strings, such as git
    arguments several calls share."""
    bound: dict[str, str | list[str]] = {}
    value: ast.expr | None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        else:
            continue
        if not isinstance(target, ast.Name):
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            bound[target.id] = value.value
        elif (strings := _strings(value)) is not None:
            bound[target.id] = strings
    return bound


def _module_file(module: str) -> str | None:
    """The package file that defines `module`, relative to the root, or `None` for any other."""
    stem = module.replace(".", "/")
    for candidate in (f"src/{stem}.py", f"src/{stem}/__init__.py"):
        if (ROOT / candidate).is_file():
            return candidate
    return None


def _imported_from(node: ast.ImportFrom, file: str) -> str:
    """The absolute module a `from … import` in `file` names: a relative one is resolved against
    the package `file` is in, one level up for each dot past the first."""
    if not node.level:
        return node.module or ""
    package = Path(file).relative_to("src").with_suffix("").parts[:-1]
    base = package[: len(package) - (node.level - 1)]
    return ".".join([*base, *([node.module] if node.module else [])])


def _bindings(tree: ast.Module, file: str) -> Bindings:
    """The file's own top-level functions, and what each of its imports binds."""
    functions = {
        node.name: (file, node.name)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    stdlib: dict[str, tuple[str, str]] = {}
    modules: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    modules[alias.asname] = alias.name
                    continue
                # `import os.path` binds `os` as well, and `os.system` is then a call through it.
                parts = alias.name.split(".")
                modules.update(
                    {".".join(parts[:i]): ".".join(parts[:i]) for i in range(1, len(parts) + 1)}
                )
        elif isinstance(node, ast.ImportFrom):
            module = _imported_from(node, file)
            for alias in node.names:
                bound = alias.asname or alias.name
                if _module_file(f"{module}.{alias.name}") is not None:
                    modules[bound] = f"{module}.{alias.name}"
                elif (source := _module_file(module)) is not None:
                    functions[bound] = (source, alias.name)
                else:
                    stdlib[bound] = (module, alias.name)
    return Bindings(functions, stdlib, modules)


def _stdlib_launch(module: str, function: str) -> Seam | None:
    """What a call of the standard library's `module.function` starts, if anything."""
    if (module, function) in STDLIB_LAUNCHES:
        return STDLIB_LAUNCHES[module, function]
    if module == "subprocess" and function not in SUBPROCESS_INERT:
        return UNREAD
    if module == "os" and function.startswith(OS_LAUNCH_PREFIXES):
        return UNREAD
    return None


def _dotted(node: ast.expr) -> str | None:
    """`a.b.c` for an expression spelled as names and attributes, the way an import binds it."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and (owner := _dotted(node.value)) is not None:
        return f"{owner}.{node.attr}"
    return None


def _last_name(node: ast.expr) -> str:
    """The last name in a receiver: `runner`, `self._runner`, `context.runner`, and the
    `subprocess_runner` of `subprocess_runner()`, alike."""
    if isinstance(node, ast.Call):
        return _last_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else ""


def _launcher(expr: ast.expr, names: Bindings) -> Seam | None:
    """The seam the expression `expr` names, called or not, or `None` when it names none."""
    if isinstance(expr, ast.Name):
        # A name bound both ways — a `def run` beside `from subprocess import run` — is taken for
        # the launch: which binding wins depends on order, and the walk does not follow order.
        named = names.stdlib.get(expr.id)
        launch = _stdlib_launch(*named) if named else None
        package = names.functions.get(expr.id)
        return launch or (SEAMS.get(package) if package else None)
    if not isinstance(expr, ast.Attribute):
        return None
    if (module := names.modules.get(_dotted(expr.value) or "")) is not None:
        source = _module_file(module)
        return SEAMS.get((source, expr.attr)) if source else _stdlib_launch(module, expr.attr)
    if expr.attr in LOOP_LAUNCHES:
        return UNREAD
    if expr.attr == "run" and _last_name(expr.value).endswith("runner"):
        return LAUNCH
    return None


def _seam_of(call: ast.Call, names: Bindings) -> Seam | None:
    """The seam `call` starts a process through, or `None` when it starts none. A `Runner` shows
    itself by its receiver's name, and any `.run` by an argv literal handed to it: a runner held
    under another name still shows itself by what it is given."""
    func = call.func
    literal = bool(call.args) and isinstance(call.args[0], (ast.List, ast.Tuple, ast.Starred))
    if isinstance(func, ast.Attribute) and func.attr == "run" and literal:
        return LAUNCH
    return _launcher(func, names)


def _argv(
    call: ast.Call, seam: Seam, constants: dict[str, str | list[str]]
) -> tuple[tuple[str | None, ...] | None, bool]:
    """What the walk reads of the argv `call` hands `seam`, and whether it read all of it."""
    if not seam.reads or len(call.args) <= seam.at:
        return None, False
    given = call.args[seam.at]
    if seam.spread:
        nodes = call.args[seam.at :]
    elif isinstance(given, (ast.List, ast.Tuple)):
        nodes = given.elts
    else:
        # A list the walk cannot see into reads as a spread of it: a module constant's strings,
        # or else an end to the reading.
        nodes = [ast.Starred(value=given, ctx=ast.Load())]
    # A value the walk cannot read, such as `-C`'s path, is `None` and does not end the reading; a
    # spread does, unless it is of a module constant, because its length is unknown. A name bound
    # to a module constant reads as the constant.
    parts: list[str | None] = list(seam.program)
    whole = True
    for node in nodes:
        named = constants.get(node.id) if isinstance(node, ast.Name) else None
        spread = None
        if isinstance(node, ast.Starred) and isinstance(node.value, ast.Name):
            spread = constants.get(node.value.id)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            parts.append(node.value)
        elif isinstance(named, str):
            parts.append(named)
        elif isinstance(spread, list):
            parts.extend(spread)
        elif isinstance(node, ast.Starred):
            parts.append(None)
            whole = False
            break
        else:
            parts.append(None)
    deciding = 1
    if parts[:1] == ["git"]:
        while len(parts) >= 3 and parts[1] in GIT_VALUED_OPTIONS:
            del parts[1:3]
        deciding = 2
    if len(parts) < deciding or None in parts[:deciding]:
        return None, whole
    return tuple(parts), whole


def _scoped(node: ast.AST, scope: tuple[str, ...] = ()) -> Iterator[tuple[ast.AST, str]]:
    """Every node under `node`, with the dotted name of the function or class it sits in. An
    annotation is left out: `subprocess.Popen[bytes]` names a type and starts nothing."""
    for field, value in ast.iter_fields(node):
        if field in ("annotation", "returns"):
            continue
        for child in value if isinstance(value, list) else [value]:
            if not isinstance(child, ast.AST):
                continue
            yield child, ".".join(scope) or "<module>"
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                yield from _scoped(child, (*scope, child.name))
            else:
                yield from _scoped(child, scope)


def _handed_on(tree: ast.Module) -> set[int]:
    """The nodes a reference cannot be: what a call calls, and the owner part of an attribute."""
    return {
        id(part)
        for node in ast.walk(tree)
        for part in (
            [node.func]
            if isinstance(node, ast.Call)
            else [node.value]
            if isinstance(node, ast.Attribute)
            else []
        )
    }


def _star_launches(node: ast.ImportFrom, file: str) -> bool:
    """Whether `from <module> import *` binds launchers the walk cannot then name."""
    module = _imported_from(node, file)
    source = _module_file(module)
    return any(alias.name == "*" for alias in node.names) and (
        module in LAUNCHER_MODULES or any(seam_file == source for seam_file, _ in SEAMS)
    )


def _seam_calls_in(source: str, file: str) -> list[SeamCall]:
    """Every launch in `source`, read as the package file `file`: each call that starts a process,
    and each place a launcher is handed on unread — named without being called (`partial`, a
    callback, an alias) or star-imported — which the walk cannot follow to its call."""
    tree = ast.parse(source)
    names, constants = _bindings(tree, file), _constants(tree)
    handed_on = _handed_on(tree)
    found = []
    for node, function in _scoped(tree):
        if isinstance(node, ast.Call) and (seam := _seam_of(node, names)) is not None:
            found.append(SeamCall(file, node.lineno, function, *_argv(node, seam, constants)))
        elif (
            isinstance(node, (ast.Name, ast.Attribute))
            and isinstance(node.ctx, ast.Load)
            and id(node) not in handed_on
            and _launcher(node, names) is not None
        ) or (isinstance(node, ast.ImportFrom) and _star_launches(node, file)):
            found.append(SeamCall(file, node.lineno, function, None, False))
    return found


def seam_calls(root: Path) -> list[SeamCall]:
    """Every call under `root` that starts a process, and what the walk read of its argv."""
    return [
        call
        for path in _package_files(root)
        for call in _seam_calls_in(
            path.read_text(encoding="utf-8"), path.relative_to(ROOT).as_posix()
        )
    ]


_RUNNER = re.compile(r"\bRunner\b")


def _is_runner(annotation: ast.expr | None) -> bool:
    return annotation is not None and _RUNNER.search(ast.unparse(annotation)) is not None


def misnamed_runners(source: str) -> list[tuple[int, str]]:
    """`(line, name)` for each parameter, field, variable or function in `source` that holds or
    returns a `Runner` — annotated so, or assigned from a call to a function whose name ends in
    `runner` — under a name that does not end in `runner`, which is how the walk knows a runner's
    `.run` when it is not handed a literal."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.arg):
            held = [(node.arg, _is_runner(node.annotation))]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            held = [(node.name, _is_runner(node.returns))]
        elif isinstance(node, ast.AnnAssign):
            held = [(_last_name(node.target), _is_runner(node.annotation))]
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            made = _last_name(node.value.func).endswith("runner")
            held = [(_last_name(target), made) for target in node.targets]
        else:
            continue
        found.extend(
            (node.lineno, name) for name, holds in held if holds and not name.endswith("runner")
        )
    return found


def _declared(call: SeamCall) -> bool:
    return (call.file, call.function) in PASS_THROUGH or (call.file, call.function) in SEAMS


def _row(argv: tuple[str | None, ...]) -> str | None:
    return next((row for prefix, row in NETWORK.items() if argv[: len(prefix)] == prefix), None)


def _local(argv: tuple[str | None, ...], whole: bool) -> bool:
    if argv[0] == "git" and any(
        part is not None and part.startswith(GIT_REMOTE_OPTIONS) for part in argv
    ):
        return False
    # An argv git was not read whole of is local only when what was not read are paths after
    # `--`: before it, an element the walk could not read could be an option such as `--remote`.
    if argv[0] == "git" and not whole and None in argv[: _end_of_options(argv)]:
        return False
    return any(argv[: len(prefix)] == prefix for prefix in LOCAL) or (whole and argv in LOCAL_WHOLE)


def _end_of_options(argv: tuple[str | None, ...]) -> int:
    """Where `--` ends git's options in `argv`, or the end of `argv` when it does not."""
    return argv.index("--") if "--" in argv else len(argv)


def unclassified(calls: list[SeamCall]) -> list[SeamCall]:
    """The calls that run a program in neither `NETWORK` nor `LOCAL`."""
    return [
        c
        for c in calls
        if c.argv is not None and _row(c.argv) is None and not _local(c.argv, c.whole)
    ]


def github_files() -> set[str]:
    """Every file stayfixed's templates write under a `.github/` directory, by the path it is
    written at: a file there is one GitHub acts on. The project's workflow is the one written
    there from a template outside one, so its path is `init`'s own constant."""
    from stayfixed.project.templates import CI_WORKFLOW

    shipped = {
        "/".join(parts[parts.index(".github") :])
        for path in TEMPLATES.rglob("*")
        if path.is_file() and ".github" in (parts := path.relative_to(TEMPLATES).parts)
    }
    return shipped | {CI_WORKFLOW}


def outbound_programs(root: Path) -> set[str]:
    """The README row keys the calls under `root` can reach, and every file the templates write
    under `.github/`."""
    calls = seam_calls(root)
    rows = {row for c in calls if c.argv is not None and (row := _row(c.argv)) is not None}
    passed = (PASS_THROUGH.get((c.file, c.function), NO_ROWS) for c in calls if c.argv is None)
    rows.update(*passed)
    return rows | github_files()


def readme_outbound_rows() -> set[str]:
    """The first code span of each row's Program cell in README's network section."""
    match = _SENDS_SECTION.search(README.read_text(encoding="utf-8"))
    assert match, "README.md has no ## What stayfixed sends where section"
    keys = []
    for line in match.group(1).splitlines():
        if not line.startswith("| ") or line.startswith("| Program |"):
            continue
        cells = line.strip("|").split(" | ")
        span = _CODE_SPAN.search(cells[0])
        assert len(cells) == 4 and span is not None, line
        keys.append(span.group(1))
    # One row per key: a second row for a program would be two declarations that can disagree.
    assert len(keys) == len(set(keys)), keys
    return set(keys)


def test_no_module_imports_a_network_module() -> None:
    # `urllib.parse` and `http.HTTPStatus` reach nothing, so the match is on modules, not roots.
    # Mutation (declared): `import subprocess` in src/stayfixed/runner.py becomes
    # `import socket, subprocess`. Mutation: the match moves to the root -> the `urllib.parse`
    # that src/stayfixed/docs/hygiene.py imports reads as `urllib.request`, and this reddens.
    # A walk-based assertion states its walk is non-empty. Mutation: `_package_files` globs only
    # the top of the package -> the floor reddens here and in the seam walk below.
    assert len(_package_files(SRC)) >= MODULES_FLOOR
    assert network_imports(SRC) == []


def test_both_import_forms_name_the_module_they_reach() -> None:
    # The tree imports no network module either way, so the walk above cannot tell the two forms
    # apart on its own. Mutation: `from a import b` stops naming `a.b` -> the second reddens.
    assert "urllib.request" in _modules(ast.parse("import urllib.request"))
    assert "urllib.request" in _modules(ast.parse("from urllib import request"))


@pytest.mark.parametrize(
    ("module", "reaches"),
    [
        ("asyncio.streams", True),
        ("logging.config", True),
        ("_socket", True),
        ("urllib.parse", False),
        ("logging", False),
    ],
)
def test_a_listed_module_reaches_a_network_with_its_submodules(module: str, reaches: bool) -> None:
    # Mutation (declared): the match drops submodules -> `asyncio.streams` passes as local.
    # Mutation: the match moves to the root -> `urllib.parse` reads as `urllib.request`'s.
    assert _reaches_a_network(module) is reaches


# Each shape a launch can take, as a package file holding it, and what the walk must read of its
# argv (`None`: a launch it cannot read, a finding until declared). The tree holds none of most of
# them, so the walk over the tree alone cannot show they are seen.
TOP, NESTED = "src/stayfixed/probe.py", "src/stayfixed/ledger/probe.py"
LAUNCH_SHAPES: dict[str, tuple[str, str, tuple[str, ...] | None]] = {
    "getoutput": (TOP, "import subprocess\nsubprocess.getoutput('curl x')", None),
    "getstatusoutput": (TOP, "import subprocess as sp\nsp.getstatusoutput('curl x')", None),
    "imported-by-name": (TOP, "from subprocess import getoutput\ngetoutput('curl x')", None),
    "runner-call": (TOP, "subprocess_runner().run(argv, root)", None),
    "runner-call-literal": (TOP, "subprocess_runner().run(['curl', 'x'], r)", ("curl", "x")),
    "other-receiver": (TOP, "launch.run(['curl', 'x'], root)", ("curl", "x")),
    "relative": (TOP, "from .gitenv import git_run\ngit_run(r, 'fetch')", ("git", "fetch")),
    "relative-up": (NESTED, "from ..gitenv import git_run as g\ng(r, 'fetch')", ("git", "fetch")),
    "relative-module": (TOP, "from . import gitenv\ngitenv.git_run(r, 'fetch')", ("git", "fetch")),
    "dotted-module": (
        TOP,
        "import stayfixed.gitenv\nstayfixed.gitenv.git_run(r, 'fetch')",
        ("git", "fetch"),
    ),
    "asyncio-exec": (
        TOP,
        "import asyncio\nasyncio.create_subprocess_exec('curl', 'x')",
        ("curl", "x"),
    ),
    "asyncio-shell": (TOP, "import asyncio\nasyncio.create_subprocess_shell('curl x')", None),
    "loop": (TOP, "loop.subprocess_exec(factory, 'curl', 'x')", None),
    "pty": (TOP, "import pty\npty.spawn(['curl', 'x'])", ("curl", "x")),
    "os-exec": (TOP, "import os\nos.execvp('curl', ['curl', 'x'])", None),
    "os-system": (TOP, "from os import system\nsystem('curl x')", None),
    "os-fexec": (TOP, "import os\nos.fexecve(fd, ['curl', 'x'], env)", None),
    "submodule-import": (TOP, "import os.path\nos.system('curl x')", None),
    "shadowed-by-def": (
        TOP,
        "from subprocess import run\ndef run(): ...\nrun(['curl', 'x'])",
        ("curl", "x"),
    ),
    "alias": (TOP, "import subprocess\nlaunch = subprocess.run", None),
    "partial": (TOP, "import functools, subprocess\nfunctools.partial(subprocess.run, x)", None),
    "callback": (TOP, "from stayfixed.gitenv import git_run\nretry(git_run, r)", None),
    "runner-handed-on": (TOP, "retry(self._runner.run, argv)", None),
    "star-subprocess": (TOP, "from subprocess import *\ngetoutput('curl x')", None),
    "star-os": (TOP, "from os import *\nsystem('curl x')", None),
    "star-seam": (TOP, "from stayfixed.gitenv import *\ngit_run(r, 'fetch')", None),
}


@pytest.mark.parametrize(("file", "source", "argv"), LAUNCH_SHAPES.values(), ids=LAUNCH_SHAPES)
def test_a_launch_of_any_shape_is_a_seam_call(
    file: str, source: str, argv: tuple[str, ...] | None
) -> None:
    # Mutations, each reddening its cases: `getoutput` joins `SUBPROCESS_INERT` (getoutput,
    # imported-by-name); a `subprocess` function not listed stops being a launch (the shell-string
    # cases); `_last_name` stops looking through a call (runner-call); `.run` is a launch by its
    # receiver alone (other-receiver); relative imports are skipped again (the three relative
    # cases); `_dotted` reads only a bare name (dotted-module); `asyncio`, `pty`, the event loop
    # and `os` each leave the launch tables (their cases); `fexec` leaves `OS_LAUNCH_PREFIXES`
    # (os-fexec). Mutation (declared): `import a.b` binds only `a.b` again (submodule-import).
    # Mutation (declared): a package function wins over a standard-library launcher of the same
    # name (shadowed-by-def). Mutation (declared): a launcher named without being called is not a
    # launch (alias, partial, callback, runner-handed-on). Mutation: a star import of a launcher's
    # module is not a launch (the three star cases).
    assert [c.argv for c in _seam_calls_in(source, file)] == [argv]


def test_a_run_that_is_not_handed_an_argv_is_not_a_launch() -> None:
    # `probe.run(context)`, `gate.run(root, config, base)` and `handler.run(view, config)` are the
    # package's own in-process `.run`s. Mutation: every `.run` is a launch -> all three are found.
    # Nor is a name that only mentions a launcher's module: an annotation, a constant, an
    # exception. Mutation: annotations are walked -> the `Popen[bytes]` annotation is found.
    source = "probe.run(context)\ngate.run(root, config, base)\nhandler.run(view, config)\n"
    source += "import subprocess\nraise subprocess.TimeoutExpired(args, 1)\n"
    source += "def f(p: subprocess.Popen[bytes]) -> None:\n    stdin = subprocess.DEVNULL\n"
    source += "from os import path\nimport os.path\nos.path.join(a, b)"
    assert _seam_calls_in(source, "src/stayfixed/assess/probe.py") == []


def test_every_seam_call_resolves_or_is_declared() -> None:
    # Mutation (declared): `PASS_THROUGH` loses `release/notes.py`'s `build` -> its `towncrier`
    # launch is unread and undeclared, and this reddens. Mutation: `SEAMS` loses `setup/run.py`'s
    # `_ask` -> its forwarding launch is a call site of its own, and this reddens.
    calls = seam_calls(SRC)
    # A walk-based assertion states its walk is non-empty: a seam the walk stopped recognising
    # would take its calls out of every check here and leave them all green. Mutation:
    # `_package_files` globs only the top of the package -> the floor reddens. Mutation: the runner
    # receiver must be named exactly `Runner` -> the launches not handed a literal drop out, and
    # the declarations test below reddens on the entries they leave naming nothing.
    assert len(calls) >= SEAM_CALLS_FLOOR, len(calls)
    assert [c for c in calls if c.argv is None and not _declared(c)] == []


def test_every_declaration_names_a_live_call_site() -> None:
    # A `SEAMS` or `PASS_THROUGH` entry whose call site moved or went would go on exempting a
    # name nothing launches from, ready for the next launch that takes it. Mutation: rename the
    # `_custom.run` entry's function -> it names nothing, and this reddens.
    unread = {(c.file, c.function) for c in seam_calls(SRC) if c.argv is None}
    assert [key for key in (*SEAMS, *PASS_THROUGH) if key not in unread] == []


def test_every_program_a_seam_call_runs_is_classified() -> None:
    # Mutation (declared): `("git", "grep")` leaves `LOCAL` -> `assess`'s marker probe runs a
    # program in neither table, and this reddens. Mutation: `-C` leaves `GIT_VALUED_OPTIONS` ->
    # `overlay publish-template`'s `git -C <clone> push` reads as a program called `-C`.
    assert unclassified(seam_calls(SRC)) == []


@pytest.mark.parametrize(
    "source",
    [
        "git_run(root, 'remote', 'update')",
        "git_run(root, 'remote', *more)",
        "git_run(root, 'archive', '--remote=git@example.com:x', 'HEAD')",
        "git_run(root, 'archive', '--format=tar', '-o', out, '--remote', url, 'HEAD')",
        "git_run(root, 'worktree', 'add', path)",
        "git_run(root, 'archive', *opts)",
        "git_run(root, 'ls-files', *opts, '--', *paths)",
    ],
    ids=[
        "remote-update",
        "remote-spread",
        "archive-remote",
        "archive-remote-late",
        "worktree-add",
        "spread-options",
        "spread-before-paths",
    ],
)
def test_a_local_subcommand_in_a_form_that_reaches_a_remote_is_unclassified(source: str) -> None:
    # `LOCAL` is as narrow as each subcommand's other forms need. Mutations: `("git", "remote")`
    # back in `LOCAL` -> the two `remote` cases pass; `GIT_REMOTE_OPTIONS` emptied -> the two
    # `archive` cases pass; `("git", "worktree")` for `("git", "worktree", "list")` ->
    # worktree-add. Mutation (declared): an argv not read whole is local whatever it did not read
    # -> the two spread cases pass, though the spread could hold `--remote`.
    calls = _seam_calls_in(f"from stayfixed.gitenv import git_run\n{source}", "src/stayfixed/x.py")
    assert unclassified(calls) == calls != []


def test_an_argv_read_up_to_its_paths_is_still_local() -> None:
    # The fail-closed rule above must not refuse the tree's own shape: options read whole, and
    # what is not read only paths after `--`, as `git ls-files … -- *paths` passes them.
    source = "from stayfixed.gitenv import git_run\ngit_run(root, 'ls-files', '-z', '--', *paths)"
    calls = _seam_calls_in(source, "src/stayfixed/x.py")
    assert calls and unclassified(calls) == []


def test_every_runner_is_named_as_one() -> None:
    # The walk knows a `Runner`'s `.run` by its receiver's name when it is not handed a literal, so
    # that name is held here: every parameter, field, variable and function that holds or returns
    # one ends in `runner`. Mutation: the check reads no annotation -> the probe's `launch` passes.
    assert misnamed_runners("def f(launch: Runner) -> None: ...") == [(1, "launch")]
    assert misnamed_runners("go = subprocess_runner()") == [(1, "go")]
    assert [
        (p, m) for p in _package_files(SRC) if (m := misnamed_runners(p.read_text("utf-8")))
    ] == []


def test_the_plugin_installs_reach_the_rows_their_entry_names() -> None:
    # `PASS_THROUGH` names `_install_plugins`'s rows by hand, because its argvs are built by
    # lambdas the walk does not call. This calls them. Mutation: `_PLUGIN_INSTALL["codex"]`
    # builds a `codex mcp add` -> it reaches no row, and this reddens.
    from stayfixed.setup.run import _MARKETPLACE_ADD, _PLUGIN_INSTALL

    builders: list[tuple[Callable[[str], list[str]], str]] = [
        *((build, "owner/marketplace") for build in _MARKETPLACE_ADD.values()),
        *((build, "plugin@marketplace") for build in _PLUGIN_INSTALL.values()),
    ]
    argvs = [build(value) for build, value in builders]
    rows = {_row(tuple(argv)) for argv in argvs}
    assert rows == PASS_THROUGH["src/stayfixed/setup/run.py", "_install_plugins"]


def test_the_readme_declares_every_program_that_reaches_a_network() -> None:
    # Both directions: a call site with no row is an undisclosed destination, which the
    # directory's security scan rejects; a row with no call site is a promise about nothing.
    # Every file the templates write under `.github/` is a row as well, because GitHub runs it.
    # Mutation (declared): the README drops the `git fetch` row. Mutation: the README drops the
    # `.github/dependabot.yml` row -> this reddens.
    assert outbound_programs(SRC) == readme_outbound_rows()
