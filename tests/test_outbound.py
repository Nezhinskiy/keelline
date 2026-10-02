"""`README.md`'s "What stayfixed sends where", held to the code.

The section declares every program stayfixed starts that can reach a network, and every file its
templates write under `.github/`, which GitHub runs. This module holds the section's Program
column to both, in both directions: a *network* launch with no row is an undisclosed
destination, which the plugin directory's security scan rejects, and a row with no launch is a
promise about nothing. What a launch is, and what the walk that finds them cannot see, is
`tests/outbound/walk.py`'s docstring; what each launch may reach is declared in
`tests/outbound/declarations.py`.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterable
from itertools import pairwise
from pathlib import Path

import pytest

from tests.outbound.declarations import (
    GIT_CONFIG_KEYS,
    GIT_GLOBAL_OPTIONS,
    GIT_REMOTE_OPTIONS,
    LOCAL,
    LOCAL_WHOLE,
    NATIVE_MODULES,
    NETWORK,
    NETWORK_MODULES,
    NO_ROWS,
    OPERANDS,
    PASS_THROUGH,
    ROOT_LAUNCHERS,
)
from tests.outbound.walk import (
    ROOT,
    SRC,
    Element,
    Launch,
    Unread,
    Walk,
    imported_modules,
    imports,
    misnamed_runners,
    package_files,
)

README = ROOT / "README.md"
TEMPLATES = SRC / "templates"
WALK = Walk(ROOT_LAUNCHERS)
# Vacuity floors, not coverage: well under what the walk finds today, so that churn never trips
# one and a walk that stopped seeing the package does.
LAUNCHES_FLOOR = 80
MODULES_FLOOR = 120
# What ends the options in an argv, after which every element is an operand, read or not.
END_OF_OPTIONS = ("--", "--end-of-options")
# The section, everything between its heading and the next `## ` heading, and a code span.
_SENDS_SECTION = re.compile(
    r"^## What stayfixed sends where\n(.*?)(?=^## )", re.MULTILINE | re.DOTALL
)
_CODE_SPAN = re.compile(r"`([^`]+)`")

Key = tuple[str, str, str]
FORBIDDEN_MODULES = NETWORK_MODULES | NATIVE_MODULES


def _within(module: str, listed: Iterable[str]) -> bool:
    return any(module == entry or module.startswith(f"{entry}.") for entry in listed)


def forbidden_imports(root: Path) -> list[tuple[str, str]]:
    """`(file, module)` for each network or native module a file under `root` imports."""
    return [(file, module) for file, module in imports(root) if _within(module, FORBIDDEN_MODULES)]


def _key(launch: Launch, element: Unread) -> Key:
    return launch.file, launch.function, element.text


def _options(argv: tuple[Element, ...]) -> tuple[Element, ...]:
    """The elements of `argv` before its options end."""
    ends = [at for at, part in enumerate(argv) if part in END_OF_OPTIONS]
    return argv[: ends[0]] if ends else argv


def _command(argv: tuple[Element, ...]) -> tuple[Element, ...] | None:
    """`argv` as the tables match it, git's global options taken out; `None` when one of them
    sets configuration outside `GIT_CONFIG_KEYS`."""
    if argv[:1] != ("git",):
        return argv
    at = 1
    while at < len(argv) and argv[at] in GIT_GLOBAL_OPTIONS:
        option = str(argv[at])
        value = argv[at + 1] if at + 1 < len(argv) else None
        configures = option == "-c" and isinstance(value, str)
        if configures and str(value).partition("=")[0] not in GIT_CONFIG_KEYS:
            return None
        at += 1 + GIT_GLOBAL_OPTIONS[option]
    return ("git", *argv[at:])


def _row(command: tuple[Element, ...]) -> str | None:
    return next((row for prefix, row in NETWORK.items() if command[: len(prefix)] == prefix), None)


def _local(command: tuple[Element, ...], options: tuple[Element, ...]) -> bool:
    if command[0] == "git" and any(
        isinstance(part, str) and part.startswith(GIT_REMOTE_OPTIONS) for part in options
    ):
        return False
    return any(command[: len(prefix)] == prefix for prefix in LOCAL) or command in LOCAL_WHOLE


def classify(launch: Launch) -> tuple[frozenset[str] | None, set[Key]]:
    """The README rows `launch` can reach — none for a local one — or `None` when it is
    unclassified; and the declarations that answer rests on.

    A launch the walk cannot read the program of is declared in `PASS_THROUGH` by its first
    unread element, or is unclassified. Otherwise its program decides: git's global options must
    be read or declared in `OPERANDS`, since one of them can change what the subcommand after
    them does; a network launch is its row whatever follows; and a launch is local only when
    every element before its options end is read or declared, because an unread one can be an
    option such as `--remote`.
    """
    unread = [part for part in launch.argv if isinstance(part, Unread)]
    if unread and (key := _key(launch, unread[0])) in PASS_THROUGH:
        return PASS_THROUGH[key], {key}
    command = _command(launch.argv)
    if command is None:
        return None, set()
    global_options = launch.argv[1 : len(launch.argv) - len(command) + 1]
    options = _options(launch.argv)
    if (row := _row(command)) is not None:
        relied = {_key(launch, part) for part in global_options if isinstance(part, Unread)}
        return (frozenset({row}), relied) if relied <= OPERANDS.keys() else (None, set())
    relied = {_key(launch, part) for part in options if isinstance(part, Unread)}
    if _local(command, options) and relied <= OPERANDS.keys():
        return NO_ROWS, relied
    return None, set()


def unclassified(launches: list[Launch]) -> list[Launch]:
    """The launches that reach neither a row nor only this machine, and are not declared."""
    return [launch for launch in launches if classify(launch)[0] is None]


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


def outbound_programs(launches: list[Launch]) -> set[str]:
    """The README rows `launches` can reach, and every file the templates write under
    `.github/`."""
    rows = set().union(*(classify(launch)[0] or NO_ROWS for launch in launches))
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


def _plugin_installs() -> list[tuple[str, ...]]:
    """Every argv `_install_plugins` builds, from the lambdas it builds them with."""
    from stayfixed.setup.run import _MARKETPLACE_ADD, _PLUGIN_INSTALL

    builders: list[tuple[Callable[[str], list[str]], str]] = [
        *((build, "owner/marketplace") for build in _MARKETPLACE_ADD.values()),
        *((build, "plugin@marketplace") for build in _PLUGIN_INSTALL.values()),
    ]
    return [tuple(build(value)) for build, value in builders]


def _shown(argv: tuple[Element, ...]) -> tuple[str | None, ...]:
    return tuple(None if isinstance(part, Unread) else part for part in argv)


def test_no_module_imports_a_network_or_native_module() -> None:
    # `urllib.parse` and `http.HTTPStatus` reach nothing, so the match is on modules, not roots.
    # The entries in `mutations/` that name this test are its declared mutations. By hand:
    # src/stayfixed/runner.py imports `ctypes` -> this reddens; the match moves to the root ->
    # the `urllib.parse` that src/stayfixed/docs/hygiene.py imports reads as `urllib.request`. A
    # walk-based assertion states its walk is non-empty: `package_files` globs only the top of
    # the package -> the floor reddens.
    assert len(package_files(SRC)) >= MODULES_FLOOR
    assert forbidden_imports(SRC) == []


def test_both_import_forms_name_the_module_they_reach() -> None:
    # The tree imports no forbidden module either way, so the walk above cannot tell the two
    # forms apart on its own. Mutation: `import a.b` names only `a` -> the first reddens.
    # Mutation: `from a import b` stops naming `a.b` -> the second reddens.
    assert "urllib.request" in imported_modules(ast.parse("import urllib.request"))
    assert "urllib.request" in imported_modules(ast.parse("from urllib import request"))


@pytest.mark.parametrize(
    ("module", "forbidden"),
    [
        ("asyncio.streams", True),
        ("logging.config", True),
        ("_socket", True),
        ("ctypes.util", True),
        ("_posixsubprocess", True),
        ("urllib.parse", False),
        ("logging", False),
    ],
)
def test_a_listed_module_is_forbidden_with_its_submodules(module: str, forbidden: bool) -> None:
    # The entries in `mutations/` that name this test are its declared mutations. By hand: the
    # match moves to the root -> `urllib.parse` reads as `urllib.request`'s.
    assert _within(module, FORBIDDEN_MODULES) is forbidden


# Each shape a launch can take, as a package file holding it, and what the walk must read of its
# argv (`None`: an element it cannot read). The tree holds none of most of them, so the walk over
# the tree alone cannot show they are seen.
TOP, NESTED = "src/stayfixed/probe.py", "src/stayfixed/ledger/probe.py"
GIT_RUN = "from stayfixed.gitenv import git_run\n"
LAUNCH_SHAPES: dict[str, tuple[str, str, tuple[str | None, ...]]] = {
    "getoutput": (TOP, "import subprocess\nsubprocess.getoutput('curl x')", (None,)),
    "getstatusoutput": (TOP, "import subprocess as sp\nsp.getstatusoutput('curl x')", (None,)),
    "imported-by-name": (TOP, "from subprocess import getoutput\ngetoutput('curl x')", (None,)),
    "keyword-args": (TOP, "import subprocess\nsubprocess.run(args=['curl', 'x'])", ("curl", "x")),
    "runner-call": (TOP, "subprocess_runner().run(argv, root)", (None,)),
    "runner-call-literal": (TOP, "subprocess_runner().run(['curl', 'x'], r)", ("curl", "x")),
    "other-receiver": (TOP, "launch.run(['curl', 'x'], root)", ("curl", "x")),
    "other-receiver-keyword": (TOP, "launch.run(argv=['curl', 'x'], cwd=r)", ("curl", "x")),
    "relative": (TOP, "from .gitenv import git_run\ngit_run(r, 'fetch')", ("git", "fetch")),
    "relative-up": (NESTED, "from ..gitenv import git_run as g\ng(r, 'fetch')", ("git", "fetch")),
    "relative-module": (TOP, "from . import gitenv\ngitenv.git_run(r, 'fetch')", ("git", "fetch")),
    "dotted-module": (
        TOP,
        "import stayfixed.gitenv\nstayfixed.gitenv.git_run(r, 'fetch')",
        ("git", "fetch"),
    ),
    "re-export": (
        TOP,
        "from stayfixed.memory.store import git_run as g\ng(r, 'push', 'origin', 'HEAD')",
        ("git", "push", "origin", "HEAD"),
    ),
    "re-export-module": (
        TOP,
        "from stayfixed.memory import store\nstore.git_run(r, 'push')",
        ("git", "push"),
    ),
    "derived": (TOP, "from stayfixed.memory.store import _git\n_git(r, 'push')", ("git", "push")),
    "derived-here": (
        TOP,
        f"{GIT_RUN}def ask(r, *args):\n    return git_run(r, '-c', 'x=y', *args)\nask(r, 'push')",
        ("git", "-c", "x=y", "push"),
    ),
    "derived-list": (
        TOP,
        "def gh(runner, argv, cwd):\n    return runner.run(['gh', *argv], cwd)\ngh(r, ['api'], c)",
        ("gh", "api"),
    ),
    "asyncio-exec": (
        TOP,
        "import asyncio\nasyncio.create_subprocess_exec('curl', 'x')",
        ("curl", "x"),
    ),
    "asyncio-shell": (TOP, "import asyncio\nasyncio.create_subprocess_shell('curl x')", (None,)),
    "loop": (TOP, "loop.subprocess_exec(factory, 'curl', 'x')", (None,)),
    "pty": (TOP, "import pty\npty.spawn(['curl', 'x'])", ("curl", "x")),
    "os-exec": (TOP, "import os\nos.execvp('curl', ['curl', 'x'])", (None,)),
    "os-system": (TOP, "from os import system\nsystem('curl x')", (None,)),
    "os-fexec": (TOP, "import os\nos.fexecve(fd, ['curl', 'x'], env)", (None,)),
    "posix": (TOP, "import posix\nposix.system('curl x')", (None,)),
    "nt": (TOP, "from nt import system\nsystem('curl x')", (None,)),
    "submodule-import": (TOP, "import os.path\nos.system('curl x')", (None,)),
    "shadowed-by-def": (
        TOP,
        "from subprocess import run\ndef run(): ...\nrun(['curl', 'x'])",
        ("curl", "x"),
    ),
    "alias": (TOP, "import subprocess\nlaunch = subprocess.run", (None,)),
    "partial": (TOP, "import functools, subprocess\nfunctools.partial(subprocess.run, x)", (None,)),
    "dunder-call": (TOP, "import subprocess\nsubprocess.run.__call__(['curl', 'x'])", (None,)),
    "in-annotation": (
        TOP,
        "import subprocess\ndef f(x: subprocess.run(['curl', 'x'])): pass",
        ("curl", "x"),
    ),
    "in-annotation-argument": (
        TOP,
        "import subprocess\ndef f(x: g(subprocess.run)): pass",
        (None,),
    ),
    "callback": (TOP, f"{GIT_RUN}retry(git_run, r)", (None,)),
    "runner-handed-on": (TOP, "retry(self._runner.run, argv)", (None,)),
    "star-subprocess": (TOP, "from subprocess import *\ngetoutput('curl x')", (None,)),
    "star-os": (TOP, "from os import *\nsystem('curl x')", (None,)),
    "star-posix": (TOP, "from posix import *\nsystem('curl x')", (None,)),
    "star-launcher": (TOP, "from stayfixed.gitenv import *\ngit_run(r, 'fetch')", (None,)),
    "star-re-export": (
        TOP,
        "from stayfixed.guards.attribute import *\ngit_run(r, 'push')",
        (None,),
    ),
    "method-forwarder": (
        TOP,
        f"{GIT_RUN}class G:\n    def ask(self, *args):\n        return git_run(r, *args)",
        ("git", None),
    ),
}


@pytest.mark.parametrize(("file", "source", "argv"), LAUNCH_SHAPES.values(), ids=LAUNCH_SHAPES)
def test_a_launch_of_any_shape_is_found(
    file: str, source: str, argv: tuple[str | None, ...]
) -> None:
    # One case per shape, so that each is proved seen on its own. The entries in `mutations/`
    # that name this test redden the cases they list. By hand, each reddening its cases:
    # `getoutput` joins `SUBPROCESS_INERT` (getoutput, imported-by-name); `last_name` stops
    # looking through a call (runner-call); `_dotted` reads only a bare name (dotted-module);
    # `asyncio`, `pty`, the event loop and `os` each leave the launcher tables (their cases);
    # `fexec` leaves `OS_LAUNCH_PREFIXES` (os-fexec); `_derive` derives nothing (the three
    # derived cases); `LAUNCHER_MODULES` loses `subprocess` and `os` (star-subprocess, star-os).
    assert [_shown(launch.argv) for launch in WALK.launches_in(source, file)] == [argv]


def test_what_only_names_a_launcher_is_not_a_launch() -> None:
    # `probe.run(context)`, `gate.run(root, config, base)` and `handler.run(view, config)` are the
    # package's own in-process `.run`s. Mutation: every `.run` is a launch -> all three are found.
    # Nor is a name that only mentions a launcher's module: an annotation, a constant, an
    # exception. Mutation: the reference check runs inside annotations -> `Popen[bytes]` is found.
    # Nor a class `isinstance` or `issubclass` compares. Mutation: `CLASS_CHECKS` is emptied ->
    # the last two lines' `Popen`s are found.
    source = "probe.run(context)\ngate.run(root, config, base)\nhandler.run(view, config)\n"
    source += "import subprocess\nraise subprocess.TimeoutExpired(args, 1)\n"
    source += "def f(p: subprocess.Popen[bytes]) -> None:\n    stdin = subprocess.DEVNULL\n"
    source += "from os import path\nimport os.path\nos.path.join(a, b)\n"
    source += "isinstance(p, subprocess.Popen)\nissubclass(t, (int, subprocess.Popen))"
    assert WALK.launches_in(source, "src/stayfixed/assess/probe.py") == []


def test_every_launch_is_classified() -> None:
    # The entries in `mutations/` that name this test are its declared mutations. By hand:
    # `OPERANDS` loses `gitenv`'s `base` -> `merge-base` hands an unread element before its
    # options end; `-C` leaves `GIT_GLOBAL_OPTIONS` -> `overlay publish-template`'s
    # `git -C <clone> push` matches no table.
    launches = WALK.launches(SRC)
    # A walk-based assertion states its walk is non-empty: a launcher the walk stopped
    # recognising would take its launches out of every check here and leave them all green.
    # Mutation: `package_files` globs only the top of the package -> the floor reddens.
    assert len(launches) >= LAUNCHES_FLOOR, len(launches)
    assert unclassified(launches) == []


def test_the_declarations_name_exactly_what_the_classification_rests_on() -> None:
    # Equality, both ways: an entry whose launch moved or went would go on exempting a value
    # nothing hands, ready for the next launch that hands it. The entry in `mutations/` that
    # names this test adds such an entry. By hand: the `_custom.run` entry's function is renamed
    # -> it names nothing, and the launch it named is undeclared.
    relied = set().union(*(classify(launch)[1] for launch in WALK.launches(SRC)))
    assert relied == PASS_THROUGH.keys() | OPERANDS.keys()


def test_a_declaration_covers_only_the_launch_it_names() -> None:
    # A declaration is about one value handed to one launch, so a second launch with a different
    # argv in a declared function is unclassified. The entry in `mutations/` that names this test
    # keys a declaration on its function alone again, and the `towncrier` entry covers the new
    # launch.
    notes = "src/stayfixed/release/notes.py"
    source = (ROOT / notes).read_text(encoding="utf-8")
    extra = "    done = runner.run(argv, root)\n    runner.run(list(EXTRA), root)\n"
    launches = WALK.launches_in(source.replace("    done = runner.run(argv, root)\n", extra), notes)
    assert [_shown(launch.argv) for launch in unclassified(launches)] == [(None,)]


def test_every_table_entry_names_a_live_launch() -> None:
    # A classification no launch uses is a promise about nothing, as a dead declaration is. The
    # plugin installs' argvs are built by lambdas, so they are counted from the lambdas. The entry
    # in `mutations/` that names this test puts a dead row in `NETWORK`. By hand, each reddening
    # its assertion: `("git", "show")` joins `LOCAL`; `("git", "stash")` joins `LOCAL_WHOLE`;
    # `--bare` joins `GIT_GLOBAL_OPTIONS`; `core.sshCommand` joins `GIT_CONFIG_KEYS`.
    commands = [
        command
        for launch in WALK.launches(SRC)
        if classify(launch)[0] is not None and (command := _command(launch.argv)) is not None
    ]
    commands += _plugin_installs()
    launched = [launch.argv for launch in WALK.launches(SRC)]

    def live(prefix: tuple[str, ...]) -> bool:
        return any(command[: len(prefix)] == prefix for command in commands)

    assert [prefix for prefix in NETWORK if not live(prefix)] == []
    assert [prefix for prefix in LOCAL if not live(prefix)] == []
    assert [whole for whole in LOCAL_WHOLE if whole not in commands] == []
    assert [o for o in GIT_GLOBAL_OPTIONS if not any(o in argv for argv in launched)] == []
    settings = {
        str(value).partition("=")[0]
        for argv in launched
        for option, value in pairwise(argv)
        if option == "-c"
    }
    assert sorted(GIT_CONFIG_KEYS - settings) == []


@pytest.mark.parametrize(
    "source",
    [
        "git_run(root, 'remote', 'update')",
        "git_run(root, 'remote', *more)",
        "git_run(root, 'archive', '--remote=git@example.com:x', 'HEAD')",
        "git_run(root, 'archive', '--format=tar', '-o', 'x.tar', '--remote', 'example', 'HEAD')",
        "git_run(root, 'worktree', 'add', '../elsewhere')",
        "git_run(root, 'archive', *opts)",
        "git_run(root, 'ls-files', *opts, '--', *paths)",
        "git_run(root, 'log', revisions)",
        "git_run(root, '-c', setting, 'status')",
        "git_run(root, '-c', 'core.sshCommand=ssh -o ProxyCommand=x', 'fetch')",
        "git_run(root, '--config-env=core.fsmonitor=VARIABLE', 'status')",
    ],
    ids=[
        "remote-update",
        "remote-spread",
        "archive-remote",
        "archive-remote-late",
        "worktree-add",
        "spread-options",
        "spread-before-paths",
        "unread-operand",
        "unread-configuration",
        "configuration-not-listed",
        "global-option-not-listed",
    ],
)
def test_a_local_subcommand_in_a_form_that_reaches_a_remote_is_unclassified(source: str) -> None:
    # `LOCAL` is as narrow as each subcommand's other forms need, and a launch is local only
    # when nothing before its options end is unread. The entries in `mutations/` that name this
    # test redden the cases they list. By hand: `("git", "remote")` back in `LOCAL` ->
    # remote-update passes; `("git", "worktree")` for `("git", "worktree", "list")` ->
    # worktree-add; `_command` skips any option before the subcommand ->
    # global-option-not-listed.
    launches = WALK.launches_in(f"{GIT_RUN}{source}", "src/stayfixed/x.py")
    assert unclassified(launches) == launches != []


@pytest.mark.parametrize("end", ["--", "--end-of-options"])
def test_an_argv_read_up_to_its_options_end_is_still_local(end: str) -> None:
    # The rule above must not refuse the tree's own shape: options read whole, and what is not
    # read only operands after the options end, whichever of git's two spellings ends them. By
    # hand: `--` leaves `END_OF_OPTIONS` -> the `--` case's `*paths` counts as an unread option,
    # and that case reddens; the same for `--end-of-options`.
    source = f"{GIT_RUN}git_run(root, 'ls-files', '-z', '{end}', *paths)"
    launches = WALK.launches_in(source, "src/stayfixed/x.py")
    assert launches and unclassified(launches) == []


def test_every_runner_is_named_as_one() -> None:
    # The walk knows a `Runner`'s `.run` by its receiver's name when it is not handed an argv
    # list, so that name is held here: every parameter, field, variable and function that holds
    # or returns one ends in `runner`. Mutation: the check reads no annotation -> the first
    # reddens. Mutation: an assignment from a `…runner()` call holds no runner -> the second.
    assert misnamed_runners("def f(launch: Runner) -> None: ...") == [(1, "launch")]
    assert misnamed_runners("go = subprocess_runner()") == [(1, "go")]
    assert [
        (p, m) for p in package_files(SRC) if (m := misnamed_runners(p.read_text("utf-8")))
    ] == []


def test_the_plugin_installs_reach_the_rows_their_entries_name() -> None:
    # `PASS_THROUGH` names `_install_plugins`'s rows by hand, because its argvs are built by
    # lambdas the walk does not call. This calls them. Mutation: `_PLUGIN_INSTALL["codex"]`
    # builds a `codex mcp add` -> it reaches no row, and this reddens.
    reached = {_row(argv) for argv in _plugin_installs()}
    declared = [rows for key, rows in PASS_THROUGH.items() if key[1] == "_install_plugins"]
    assert declared and all(rows == reached for rows in declared)


def test_the_readme_declares_every_program_that_reaches_a_network() -> None:
    # Both directions: a launch with no row is an undisclosed destination, which the directory's
    # security scan rejects; a row with no launch is a promise about nothing. Every file the
    # templates write under `.github/` is a row as well, because GitHub runs it. The entries in
    # `mutations/` that name this test are its declared mutations. By hand: the README drops the
    # `.github/dependabot.yml` row -> this reddens.
    assert outbound_programs(WALK.launches(SRC)) == readme_outbound_rows()
