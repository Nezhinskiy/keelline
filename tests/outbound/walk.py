"""The outbound walk: every process stayfixed's package starts, found in the package's syntax.

`tests/test_outbound.py` holds README.md's "What stayfixed sends where" to what this walk finds,
and this docstring is the one description of what it sees and what it cannot.

**What it finds.** A *launch* is a call that starts a process, a launcher named without being
called — handed to `functools.partial`, passed as a callback, bound to another name, used as a
base class — or a star import of a launcher module or of a package module, which can re-export
one. The standard library's launchers are `subprocess`, the `os` process functions (reached
through `os`, `posix` or `nt`), `pty.spawn`, `asyncio`'s subprocess calls and an event loop's.
The package's own start from the roots `tests/outbound/declarations.py` names and grow by
derivation: a module-level function that hands its own argv — its `*args`, or a list parameter,
as the argv's last part — to a launcher is a launcher too, read at its callers, and so is one
that hands its argv to that one. A method or a nested function that does is not, because the
walk does not follow the names it is called through: its own launch stays a finding until it is
declared. A `Runner`'s `.run` is a launcher by its receiver's name, which ends in `runner` (held
by `misnamed_runners`), or by an argv list handed to it, positionally or as `argv=`. A name is
followed through every import, relative, dotted or a re-export, to the module that defines it.

**What it reads.** Each launch's argv, element by element: a string literal, or a module
constant holding a string or a list of strings, is read; anything else is `Unread`, carrying
its source text, and a launch whose argv the walk cannot read at all — a shell string, a
launcher handed on — is one `Unread`. `isinstance` and `issubclass` only compare a class, so
a launcher named there is not handed on; nor is one named as a type in an annotation, though
a call there still runs, and is walked, when the annotation is evaluated.

**What it cannot see.** Each of these is a launch the walk returns nothing for:

- dynamic dispatch: `getattr(subprocess, "run")`, `importlib.import_module`, `__import__`,
  `sys.modules`, and code run from data by `exec`, `eval` or `pickle`;
- a launcher module bound by assignment rather than by an import (`m = subprocess`): a call
  through it is seen only when it is `.run` handed an argv list;
- a launcher named in an annotation anywhere but as a call's argument, such as `Annotated`
  metadata (`Annotated[int, subprocess.run]`), which code reading the annotation could call;
- a `Runner` reached through a subscript or a container rather than a name
  (`RUNNERS["x"].run(argv, root)`), and handed an argv that is not a list;
- a launch the standard library makes on the package's behalf: `uuid.getnode()` can run
  `ifconfig` or `ip`, and `platform.architecture()` runs `file`, because the walk reads the
  package and not the standard library;
- a process of the running interpreter that `multiprocessing` or `concurrent.futures` starts,
  which runs the package's own code rather than another program.

`ctypes`, `_posixsubprocess` and `_winapi` start a process through no launcher the walk knows,
so the outbound test forbids importing them, beside the network modules, rather than walking
them.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import cache, cached_property
from pathlib import Path
from typing import TypeAlias

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "stayfixed"


@dataclass(frozen=True)
class Launcher:
    """How a launcher takes its argv. `program` is what it puts first itself; the rest is the
    call's arguments from position `at` on when `spread`, or else the one list at position `at`
    or under `keyword`. A launcher that does not `read` takes a shell string."""

    program: tuple[str, ...] = ()
    at: int = 0
    spread: bool = False
    keyword: str | None = None
    reads: bool = True


@dataclass(frozen=True)
class Unread:
    """An argv element the walk cannot read, by its source text; `spread` when it stands for
    any number of elements."""

    text: str
    spread: bool = False


Element: TypeAlias = str | Unread


@dataclass(frozen=True)
class Launch:
    """One launch: where it is — `function` is the dotted name of the function or class it sits
    in — and its argv, as far as the walk reads it."""

    file: str
    line: int
    function: str
    argv: tuple[Element, ...]


SUBPROCESS = Launcher(keyword="args")
RUNNER = Launcher(keyword="argv")
SHELL = Launcher(reads=False)
# Every standard-library function that starts a process and takes an argv the walk can read, by
# `(module, function)`.
STDLIB_LAUNCHERS: dict[tuple[str, str], Launcher] = {
    ("subprocess", "run"): SUBPROCESS,
    ("subprocess", "Popen"): SUBPROCESS,
    ("subprocess", "call"): SUBPROCESS,
    ("subprocess", "check_call"): SUBPROCESS,
    ("subprocess", "check_output"): SUBPROCESS,
    ("pty", "spawn"): Launcher(keyword="argv"),
    ("asyncio", "create_subprocess_exec"): Launcher(spread=True),
    ("asyncio", "create_subprocess_shell"): SHELL,
}
# A call to any other `subprocess` name is a launch too — `getoutput` and `getstatusoutput` take a
# shell string — except these, which start nothing. So is a call to `os.system`, `os.popen`,
# `os.startfile` and the `exec`, `fexec`, `spawn` and `posix_spawn` families, and to an event
# loop's `subprocess_exec` and `subprocess_shell` on whatever loop a call holds. The walk reads
# none of their argvs.
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
OS_LAUNCH_PREFIXES = ("system", "popen", "startfile", "exec", "fexec", "spawn", "posix_spawn")
LOOP_LAUNCHES = frozenset({"subprocess_exec", "subprocess_shell"})
# `os` takes its process functions from `posix`, or from `nt` on Windows, so a call through either
# is a call through `os`.
OS_MODULES = frozenset({"os", "posix", "nt"})
# The modules whose names are launchers: a star import of one binds names the walk cannot follow.
LAUNCHER_MODULES = OS_MODULES | {module for module, _ in STDLIB_LAUNCHERS}
# The calls that only compare a class, by the name they are called through.
CLASS_CHECKS = frozenset({"isinstance", "issubclass"})


@dataclass(frozen=True)
class Bindings:
    """What the names in the package file `file` are bound to: `functions` maps a bare name to
    the package function it names, as `(file, function)`; `stdlib` maps one imported by name
    from the standard library to `(module, function)`; `modules` maps a name, dotted or not, to
    the module it is. A name can be bound in more than one."""

    file: str
    functions: dict[str, tuple[str, str]]
    stdlib: dict[str, tuple[str, str]]
    modules: dict[str, str]


def package_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


@cache
def _tree(file: str) -> ast.Module:
    return ast.parse((ROOT / file).read_text(encoding="utf-8"))


def imported_modules(tree: ast.Module) -> set[str]:
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


def imports(root: Path) -> list[tuple[str, str]]:
    """`(file, module)` for each module a file under `root` imports."""
    return [
        (relative(path), module)
        for path in package_files(root)
        for module in sorted(imported_modules(_tree(relative(path))))
    ]


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


@cache
def _bindings_of(file: str) -> Bindings:
    return _bindings(_tree(file), file)


def _bindings(tree: ast.Module, file: str) -> Bindings:
    """The file's own top-level functions, and what each of its imports binds, as written: a
    name imported from a package module is bound to that module's name for it, which
    `_resolved` follows."""
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
    return Bindings(file, functions, stdlib, modules)


def _resolved(
    names: Bindings, name: str, seen: frozenset[tuple[str, str]] = frozenset()
) -> Bindings:
    """What `name` is, bound as `name`: a name a package module only imports is what it imports
    there, followed to the module that defines it, so `from stayfixed.memory.store import
    git_run` is `gitenv`'s `git_run`, which `store` imports."""
    resolved = Bindings(names.file, {}, {}, {})
    if name in names.stdlib:
        resolved.stdlib[name] = names.stdlib[name]
    if name in names.modules:
        resolved.modules[name] = names.modules[name]
    if (target := names.functions.get(name)) is None:
        return resolved
    onward = Bindings(target[0], {}, {}, {})
    if target[0] != names.file and target not in seen:
        onward = _resolved(_bindings_of(target[0]), target[1], seen | {target})
    hop = target[1]
    if hop in onward.functions:
        resolved.functions[name] = onward.functions[hop]
    if hop in onward.stdlib:
        resolved.stdlib[name] = onward.stdlib[hop]
    if hop in onward.modules:
        resolved.modules[name] = onward.modules[hop]
    if not (onward.functions or onward.stdlib or onward.modules):
        # Defined here, or bound by something other than a `def` or an import.
        resolved.functions[name] = target
    return resolved


def _lookup(module: str, name: str) -> Bindings:
    """What `module.name` is, bound as `name`, followed as `_resolved` follows it."""
    if _module_file(f"{module}.{name}") is not None:
        return Bindings("", {}, {}, {name: f"{module}.{name}"})
    if (source := _module_file(module)) is None:
        return Bindings("", {}, {name: (module, name)}, {})
    return _resolved(Bindings("", {name: (source, name)}, {}, {}), name)


def _stdlib_launcher(module: str, function: str) -> Launcher | None:
    """What a call of the standard library's `module.function` starts, if anything."""
    module = "os" if module in OS_MODULES else module
    if (module, function) in STDLIB_LAUNCHERS:
        return STDLIB_LAUNCHERS[module, function]
    if module == "subprocess" and function not in SUBPROCESS_INERT:
        return SHELL
    if module == "os" and function.startswith(OS_LAUNCH_PREFIXES):
        return SHELL
    return None


def _dotted(node: ast.expr) -> str | None:
    """`a.b.c` for an expression spelled as names and attributes, the way an import binds it."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and (owner := _dotted(node.value)) is not None:
        return f"{owner}.{node.attr}"
    return None


def last_name(node: ast.expr) -> str:
    """The last name in a receiver: `runner`, `self._runner`, `context.runner`, and the
    `subprocess_runner` of `subprocess_runner()`, alike."""
    if isinstance(node, ast.Call):
        return last_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else ""


Launchers: TypeAlias = dict[tuple[str, str], Launcher]


def _module_of(names: Bindings, owner: ast.expr) -> str | None:
    """The module `owner` names, by an import of its own or one a package module re-exports."""
    dotted = _dotted(owner) or ""
    if dotted in names.modules:
        return names.modules[dotted]
    return _resolved(names, dotted).modules.get(dotted) if dotted in names.functions else None


def _bound_launcher(names: Bindings, name: str, launchers: Launchers) -> Launcher | None:
    # A name bound both ways — a `def run` beside `from subprocess import run` — is taken for the
    # launch: which binding wins depends on order, and the walk does not follow order.
    names = _resolved(names, name)
    named = names.stdlib.get(name)
    launcher = _stdlib_launcher(*named) if named else None
    package = names.functions.get(name)
    return launcher or (launchers.get(package) if package else None)


def _launcher(expr: ast.expr, names: Bindings, launchers: Launchers) -> Launcher | None:
    """The launcher the expression `expr` names, called or not, or `None` when it names none."""
    if isinstance(expr, ast.Name):
        return _bound_launcher(names, expr.id, launchers)
    if not isinstance(expr, ast.Attribute):
        return None
    if (module := _module_of(names, expr.value)) is not None:
        return _bound_launcher(_lookup(module, expr.attr), expr.attr, launchers)
    if expr.attr in LOOP_LAUNCHES:
        return SHELL
    if expr.attr == "run" and last_name(expr.value).endswith("runner"):
        return RUNNER
    return None


def _given(call: ast.Call, launcher: Launcher) -> ast.expr | None:
    """The one argv argument `call` hands a launcher that takes its argv whole."""
    if len(call.args) > launcher.at:
        return call.args[launcher.at]
    return next((k.value for k in call.keywords if k.arg and k.arg == launcher.keyword), None)


def _launcher_of(call: ast.Call, names: Bindings, launchers: Launchers) -> Launcher | None:
    """The launcher `call` starts a process through, or `None` when it starts none. Any `.run`
    handed an argv list is a `Runner`'s, so a runner held under another name still shows itself
    by what it is given."""
    if (launcher := _launcher(call.func, names, launchers)) is not None:
        return launcher
    given = _given(call, RUNNER)
    listed = isinstance(given, (ast.List, ast.Tuple, ast.Starred))
    if isinstance(call.func, ast.Attribute) and call.func.attr == "run" and listed:
        return RUNNER
    return None


def _spread(expr: ast.expr, text: str, constants: dict[str, str | list[str]]) -> list[Element]:
    """A list the walk cannot see into, read as a spread of it: a module constant's strings, or
    one `Unread` of any length."""
    named = constants.get(expr.id) if isinstance(expr, ast.Name) else None
    return list(named) if isinstance(named, list) else [Unread(text, spread=True)]


def _element(node: ast.expr, constants: dict[str, str | list[str]]) -> list[Element]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Name) and isinstance(constants.get(node.id), str):
        return [str(constants[node.id])]
    if isinstance(node, ast.Starred):
        return _spread(node.value, ast.unparse(node), constants)
    return [Unread(ast.unparse(node))]


def _argv_nodes(call: ast.Call, launcher: Launcher) -> tuple[list[ast.expr], bool] | None:
    """The argument nodes `call` hands `launcher` as its argv, past the launcher's own
    `program`, and whether they are one expression that is the whole argv, a list the walk
    cannot see into; `None` when the walk reads no argv there."""
    if not launcher.reads:
        return None
    if launcher.spread:
        return list(call.args[launcher.at :]), False
    given = _given(call, launcher)
    if given is None:
        return None
    if isinstance(given, (ast.List, ast.Tuple)):
        return list(given.elts), False
    return [given], True


def _argv(
    call: ast.Call, launcher: Launcher, constants: dict[str, str | list[str]]
) -> tuple[Element, ...]:
    """What the walk reads of the argv `call` hands `launcher`."""
    if (handed := _argv_nodes(call, launcher)) is None:
        return (Unread(ast.unparse(call.args[0] if call.args else call)),)
    nodes, whole = handed
    parts: list[Element] = list(launcher.program)
    for node in nodes:
        read = _spread(node, ast.unparse(node), constants) if whole else _element(node, constants)
        parts.extend(read)
    return tuple(parts)


Function: TypeAlias = ast.FunctionDef | ast.AsyncFunctionDef


def _handed_on(call: ast.Call, launcher: Launcher, function: Function | None) -> str | None:
    """The parameter of `function` that `call` hands `launcher` as its argv's last part — its
    `*args`, or a list parameter, spread or whole — or `None` when it hands none."""
    handed = _argv_nodes(call, launcher)
    if function is None or handed is None or not handed[0]:
        return None
    nodes, whole = handed
    tail = nodes[-1] if whole else nodes[-1].value if isinstance(nodes[-1], ast.Starred) else None
    arguments = function.args
    names = [a.arg for a in (*arguments.posonlyargs, *arguments.args)]
    if arguments.vararg is not None:
        names.append(arguments.vararg.arg)
    return tail.id if isinstance(tail, ast.Name) and tail.id in names else None


def _derived(
    call: ast.Call,
    launcher: Launcher,
    function: Function | None,
    constants: dict[str, str | list[str]],
) -> Launcher | None:
    """The launcher `function` is when `call` hands `launcher` the function's own argv, with
    nothing before it the walk cannot read: its callers' arguments are then read at each
    caller, after what this call puts first."""
    parameter = _handed_on(call, launcher, function)
    if parameter is None or function is None:
        return None
    head = _argv(call, launcher, constants)[:-1]
    if not all(isinstance(part, str) for part in head):
        return None
    program = tuple(str(part) for part in head)
    arguments = function.args
    positional = [a.arg for a in (*arguments.posonlyargs, *arguments.args)]
    if arguments.vararg is not None and parameter == arguments.vararg.arg:
        return Launcher(program, at=len(positional), spread=True)
    return Launcher(program, at=positional.index(parameter), keyword=parameter)


def _scoped(
    node: ast.AST,
    scope: tuple[str, ...] = (),
    function: Function | None = None,
    annotation: bool = False,
) -> Iterator[tuple[ast.AST, str, Function | None, bool]]:
    """Every node under `node`, with the dotted name of the function or class it sits in, the
    innermost function, and whether it sits in an annotation: there `subprocess.Popen[bytes]`
    names a type, though a call's arguments are still values when the annotation is evaluated."""
    for field, value in ast.iter_fields(node):
        arguments = isinstance(node, ast.Call) and field in ("args", "keywords")
        inside = (annotation and not arguments) or field in ("annotation", "returns")
        for child in value if isinstance(value, list) else [value]:
            if not isinstance(child, ast.AST):
                continue
            yield child, ".".join(scope) or "<module>", function, inside
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield from _scoped(child, (*scope, child.name), child, inside)
            elif isinstance(child, ast.ClassDef):
                yield from _scoped(child, (*scope, child.name), function, inside)
            else:
                yield from _scoped(child, scope, function, inside)


def _not_handed_on(tree: ast.Module) -> set[int]:
    """The nodes a launcher named there is not handed on from: what a call calls, which the
    call itself is read for, and a class `isinstance` or `issubclass` only compares."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        ids.add(id(node.func))
        if isinstance(node.func, ast.Name) and node.func.id in CLASS_CHECKS and node.args[1:]:
            compared = node.args[1]
            ids.update(map(id, compared.elts if isinstance(compared, ast.Tuple) else [compared]))
    return ids


def _star_launches(node: ast.ImportFrom, file: str) -> bool:
    """Whether `from <module> import *` can bind launchers the walk cannot then name: from a
    launcher module, or from any package module, which can re-export one."""
    module = _imported_from(node, file)
    return any(alias.name == "*" for alias in node.names) and (
        module in LAUNCHER_MODULES or _module_file(module) is not None
    )


@dataclass(frozen=True)
class _Source:
    tree: ast.Module
    file: str
    names: Bindings
    constants: dict[str, str | list[str]]


def _source(file: str, text: str | None = None) -> _Source:
    tree = _tree(file) if text is None else ast.parse(text)
    names = _bindings_of(file) if text is None else _bindings(tree, file)
    return _Source(tree, file, names, _constants(tree))


def _derive(sources: list[_Source], launchers: Launchers) -> Launchers:
    """`launchers` and every launcher derived from them in `sources`, to a fixed point."""
    found = dict(launchers)
    while True:
        added = {
            (source.file, scope): launcher
            for source in sources
            for node, scope, function, _ in _scoped(source.tree)
            # Only a module-level function: a method or a nested function is called through
            # names the walk does not bind, so as a launcher its callers would go unread.
            if isinstance(node, ast.Call)
            and "." not in scope
            and (outer := _launcher_of(node, source.names, found)) is not None
            and (launcher := _derived(node, outer, function, source.constants)) is not None
            and (source.file, scope) not in found
        }
        if not added:
            return found
        found.update(added)


def _launches(source: _Source, launchers: Launchers) -> list[Launch]:
    """Every launch in `source`: each call that starts a process, except a launcher's own
    handing on of its argv, which is read at its callers; and each place a launcher is handed on
    unread — named without being called, or star-imported — which the walk cannot follow."""
    not_handed_on = _not_handed_on(source.tree)
    found = []
    for node, scope, function, in_annotation in _scoped(source.tree):
        if isinstance(node, ast.Call):
            if (launcher := _launcher_of(node, source.names, launchers)) is None:
                continue
            if (source.file, scope) in launchers and _handed_on(node, launcher, function):
                continue
            argv = _argv(node, launcher, source.constants)
            found.append(Launch(source.file, node.lineno, scope, argv))
        elif isinstance(node, (ast.Name, ast.Attribute)):
            if (
                isinstance(node.ctx, ast.Load)
                and not in_annotation
                and id(node) not in not_handed_on
                and _launcher(node, source.names, launchers) is not None
            ):
                unread = (Unread(ast.unparse(node)),)
                found.append(Launch(source.file, node.lineno, scope, unread))
        elif isinstance(node, ast.ImportFrom) and _star_launches(node, source.file):
            found.append(Launch(source.file, node.lineno, scope, (Unread(ast.unparse(node)),)))
    return found


class Walk:
    """The walk over the package from `roots`, the package launchers it starts from."""

    def __init__(self, roots: Mapping[tuple[str, str], Launcher]) -> None:
        self.roots = dict(roots)

    @cached_property
    def launchers(self) -> Launchers:
        """Every package launcher: the roots, and every one derived from them."""
        sources = [_source(relative(path)) for path in package_files(SRC)]
        return _derive(sources, self.roots)

    def launches(self, root: Path = SRC) -> list[Launch]:
        """Every launch in the package files under `root`."""
        return [
            launch
            for path in package_files(root)
            for launch in _launches(_source(relative(path)), self.launchers)
        ]

    def launches_in(self, text: str, file: str) -> list[Launch]:
        """Every launch in `text`, read as a package file `file` beside the package's own."""
        source = _source(file, text)
        return _launches(source, _derive([source], self.launchers))


_RUNNER = re.compile(r"\bRunner\b")


def _is_runner(annotation: ast.expr | None) -> bool:
    return annotation is not None and _RUNNER.search(ast.unparse(annotation)) is not None


def misnamed_runners(source: str) -> list[tuple[int, str]]:
    """`(line, name)` for each parameter, field, variable or function in `source` that holds or
    returns a `Runner` — annotated so, or assigned from a call to a function whose name ends in
    `runner` — under a name that does not end in `runner`, which is how the walk knows a runner's
    `.run` when it is not handed an argv list."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.arg):
            held = [(node.arg, _is_runner(node.annotation))]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            held = [(node.name, _is_runner(node.returns))]
        elif isinstance(node, ast.AnnAssign):
            held = [(last_name(node.target), _is_runner(node.annotation))]
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            made = last_name(node.value.func).endswith("runner")
            held = [(last_name(target), made) for target in node.targets]
        else:
            continue
        found.extend(
            (node.lineno, name) for name, holds in held if holds and not name.endswith("runner")
        )
    return found
