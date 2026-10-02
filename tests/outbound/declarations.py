"""What stayfixed's launches may reach, declared: the policy `tests/test_outbound.py` holds the
package to, over what `tests/outbound/walk.py` finds.

The classification tables and the declarations are held both ways: a launch no entry accounts
for is a finding, and so is an entry no launch uses, because a declaration about nothing is
ready to excuse the next launch that matches it. The forbidden modules are held one way, since
nothing may import them, and a root launcher that named nothing would leave its own launch
unread, which is a finding too.
"""

from __future__ import annotations

from tests.outbound.walk import RUNNER, Launcher

# Every standard-library module that gives a process a connection of its own. A listed module
# matches with everything below it (`asyncio.streams` is `asyncio`'s), and never by its root alone:
# `urllib`, `http` and `logging` are not listed, because `urllib.parse`, `http.HTTPStatus` and a
# plain logger reach nothing, while `urllib.request`, `http.client`, `logging.handlers` and
# `logging.config` (whose `listen()` opens a socket) do. `asyncio` is listed whole although most of
# it reaches nothing: its connection calls and its subprocess calls come in through one import,
# which a match on names cannot tell apart, and the package imports it for neither. A module that
# wants it for a subprocess is an edit here that says so, and the launches it makes are walked
# like any other. `smtpd`, `asyncore` and `asynchat` are gone from 3.12 and importable on the 3.11
# floor; `_socket` and `_ssl` are what `socket` and `ssl` are built on.
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
# Every standard-library module that starts a process through no launcher the walk knows, so that
# importing one is a finding rather than a launch to read: `ctypes` (and `_ctypes`, which it is
# built on) can call the C library's `system` or `execv` directly, and `_posixsubprocess` and
# `_winapi` hold the calls `subprocess` itself is built on.
NATIVE_MODULES = frozenset({"_ctypes", "_posixsubprocess", "_winapi", "ctypes"})

# The package launchers the walk starts from, by `(file, function)`; every other is derived from
# them and from the standard library's. Neither of these two can be derived. `git_run` puts
# `-C <root>` between `git` and its caller's arguments, and the walk does not read `str(root)`;
# declared, it is taken for what it is, `git` run in the directory `root` names. The real
# `Runner`'s `.run` is a method, which the walk does not bind by name: calls reach it as
# `<…runner>.run(argv, cwd)`, which the walk knows as a `Runner`'s, and its own launch is the argv
# each of those hands it.
ROOT_LAUNCHERS: dict[tuple[str, str], Launcher] = {
    ("src/stayfixed/gitenv.py", "git_run"): Launcher(("git",), at=1, spread=True),
    ("src/stayfixed/runner.py", "_SubprocessRunner.run"): RUNNER,
}

# Where each program a launch runs can reach, by the argv prefix that decides it, git's global
# options taken out: the README row that declares it, by the row's first code span. `sh -c` runs
# the command `test attribute --command` names, which reaches wherever it reaches. A launch whose
# prefix is here is the row's whatever follows the prefix, because the row discloses the program
# and not one form of it.
NETWORK: dict[tuple[str, ...], str] = {
    ("gh",): "gh",
    ("git", "clone"): "git clone",
    ("git", "fetch"): "git fetch",
    ("git", "push"): "git push",
    ("git", "ls-remote"): "git ls-remote",
    ("claude", "plugin"): "claude plugin",
    ("codex", "plugin"): "codex plugin",
    ("pre-commit", "install"): "pre-commit install",
    ("sh", "-c"): "sh -c",
}
# The programs a launch runs that reach nothing past this machine, by argv prefix, each as narrow
# as the subcommand's other forms require: `git remote` and `git worktree` have forms that ask a
# remote or change one, so only the forms in use are listed. A launch is local only when every
# element before its options end is read, or declared in `OPERANDS`, and none is in
# `GIT_REMOTE_OPTIONS`. A launch in neither table is a finding: it has to be read and put in one.
LOCAL = frozenset(
    {
        ("git", "--version"),
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
# The global options a launch may put before git's subcommand, and whether each takes the next
# argument as its value. None of them changes which program git runs or where it reaches, except
# `-c`, whose value is configuration: it is held to `GIT_CONFIG_KEYS`. Any other option there is a
# finding, because the subcommand the tables match would then follow something unread.
GIT_GLOBAL_OPTIONS = {"-C": True, "-c": True, "--literal-pathspecs": False}
# The configuration a launch may set with `git -c`: each changes how git prints a name, or which
# repository it accepts, and never what it runs or where it reaches, as `core.sshCommand`,
# `core.fsmonitor` or `url.<base>.insteadOf` would.
GIT_CONFIG_KEYS = frozenset({"core.quotePath", "safe.bareRepository"})
# Options with which a git command that otherwise reads the local repository asks a remote instead
# (`git archive --remote=<url>`). Wherever one appears before the options end, the launch is not
# local.
GIT_REMOTE_OPTIONS = ("--remote", "--upload-pack", "--receive-pack", "--exec")

# The rows of a launch that reaches nothing past this machine.
NO_ROWS: frozenset[str] = frozenset()
# Each launch whose program the walk cannot read, and the README rows it can reach. A launch is
# keyed by `(file, function, element)`, the element being the source text of the first one the
# walk could not read: not by its line, so an edit above it leaves the entry true, and not by its
# function alone, so a launch handing a different argv in the same function is a finding. A second
# launch handing the same expression is covered by the same entry. The comment says what each runs;
# a reviewer reads it.
PASS_THROUGH: dict[tuple[str, str, str], frozenset[str]] = {
    # A project's own `[gates.custom.<name>] run`, launched as configured.
    ("src/stayfixed/assess/gates.py", "_custom.run", "list(argv)"): frozenset({"[gates.custom]"}),
    # `claude plugin marketplace add` and `codex plugin marketplace add`, then `claude plugin
    # install` and `codex plugin add`, each built by a lambda in `_MARKETPLACE_ADD` or
    # `_PLUGIN_INSTALL`, which `test_the_plugin_installs_reach_the_rows_their_entries_name` calls.
    ("src/stayfixed/setup/run.py", "_install_plugins", "add_argv_of(source)"): frozenset(
        {"claude plugin", "codex plugin"}
    ),
    ("src/stayfixed/setup/run.py", "_install_plugins", "argv"): frozenset(
        {"claude plugin", "codex plugin"}
    ),
    # `towncrier build --version X --yes [--draft]`, assembled before the call: it renders
    # `changelog.d/` into `CHANGELOG.md`.
    ("src/stayfixed/release/notes.py", "build", "argv"): NO_ROWS,
    # `git [-c core.excludesFile=…] --git-dir=… --work-tree=<empty> check-ignore --no-index
    # --stdin -z`, assembled in `asked`: the owner's own exclude files, asked about.
    ("src/stayfixed/attach/exclude.py", "unhidden_by_owner", "*asked"): NO_ROWS,
    # `hooks/run-hook.sh open --version` under the plugin root this process derived: stayfixed's
    # own hook wrapper, asked for its version.
    ("src/stayfixed/doctor/checks.py", "_wrapper", "str(root / WRAPPER)"): NO_ROWS,
}
# Each element a launch hands before its options end that the walk cannot read, keyed as
# `PASS_THROUGH` is, and why it cannot be an option that changes what the launch reaches. The
# launch is then classified by the rest of its argv.
OPERANDS: dict[tuple[str, str, str], str] = {
    ("src/stayfixed/gitenv.py", "fork_points", "base"): (
        "every caller refuses a base that starts with `-` before it asks"
    ),
    ("src/stayfixed/docs/plans.py", "touched_plans.changed", "since"): (
        "a merge base git printed, or the base `touched_plans` refused when it starts with `-`"
    ),
    ("src/stayfixed/ledger/check.py", "_base_ledger", "fork"): "a merge base git printed",
    ("src/stayfixed/guards/attribute.py", "_extract", "str(archive)"): (
        "the value of `git archive -o` and of `tar -f`, a path under the temporary directory "
        "this run made"
    ),
    ("src/stayfixed/guards/attribute.py", "_extract", "ref"): (
        "`HEAD`, or the merge base git printed"
    ),
    ("src/stayfixed/guards/commit.py", "commits_in", "rev_range"): (
        "refused when it starts with `-`, and closed by the `--` after it"
    ),
    ("src/stayfixed/guards/githooks.py", "git_path", "name"): (
        "the value of `--git-path`, always one of its callers' constants"
    ),
    ("src/stayfixed/project/detect.py", "_symbolic", "ref"): (
        "`HEAD` or `refs/remotes/origin/HEAD`, its callers' constants"
    ),
    ("src/stayfixed/assess/probes.py", "_commit_types", "f'-n{context.window}'"): (
        "`-n` and the probe's window, an integer"
    ),
    ("src/stayfixed/overlay/publish.py", "publish_template", "str(clone)"): (
        "the value of `-C`, the directory this run cloned into"
    ),
    ("src/stayfixed/overlay/publish.py", "publish_template", "message"): (
        "the value of `git commit -m`, built from stayfixed's version"
    ),
}
