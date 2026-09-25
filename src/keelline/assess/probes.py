"""The probes no gate runs: what an inventory reads from files and the git index alone.

Each probe is a small function over the repository, with no network and no tool run. Its id,
principle, severity and remedy live once, on its `Probe`; the function returns only what it saw,
and `run_probes` builds the items, so the attribute a test reads off `PROBES` is the attribute
an item carries.

**A probe that could not look says so.** Every git query runs under `QUERY_TIMEOUT_SECONDS`,
and an exit that is not one of that query's own answers — `git_run`'s `-1` included, which is a
timeout, a git that could not start, or output that is not UTF-8 — is `unread`. So is a file
the probe cannot read or parse, and a path through a symlink. `run_probes` turns `unread` into
one `could-not-look` warning per probe and never into "nothing found": an empty answer read
from a query that did not finish would say no secret is committed.

**No repository byte can end the inventory.** Everything a probe's reading can raise on
repository content is caught where it is read and becomes `unread`.

**Nothing here is printed.** A `where` label is a path the repository chose, a sha, or this
module's own words, and it goes to the machine-readable output only; the summary that reports
these items prints counts and this module's vocabulary.

Two inventory items are not built. Another tool's design-document directories are that tool's
convention, and Keelline names no other tool's convention. The test-entrypoint audit stays its
own advisory command until its candidates are triaged (its module says why).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from keelline.assess.model import Item, item
from keelline.config.paths import PathEscape, contained
from keelline.findings import Severity
from keelline.gitenv import git_run
from keelline.guards.api import contained_roots
from keelline.scaffold import EntriesError, marker_id, owned_ids

if TYPE_CHECKING:
    from keelline.config.schema import Config

# Wall-clock bound on one probe's git query. It mirrors the ledger's own bound on its local
# queries, which is private to that area: a `log --all` or a `grep` over a long history is not
# a five-second `rev-parse`, and none of these reaches the network.
QUERY_TIMEOUT_SECONDS = 30
COULD_NOT_LOOK = "could-not-look"
PROFILE = "profile"
PROFILE_NOT_SHIPPED = "profile-not-shipped"

COULD_NOT_LOOK_REMEDY = (
    "Keelline could not read what `where` names; `keelline doctor` names a settings file it "
    "cannot read, and a git query that timed out may answer once the repository is idle"
)
# Formatted with `", ".join(profiles.shipped()) or "none"`: Keelline's own listing.
PROFILE_NOT_SHIPPED_REMEDY = (
    "set [keelline] profile to a profile this Keelline ships ({shipped}), or to an empty string"
)
# Each word spelled so this line is not one of the markers it searches for.
_MARKERS = "T[O]DO|F[I]XME|X[X]X"
_SUBJECT = re.compile(r"^([a-z]+)(\([^)]*\))?!?: ")
_ENV_KEEP = (".example", ".sample", ".template")
_CODEOWNERS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")  # GitHub's order
_WORKFLOWS = ".github/workflows"
_UNOWNED = f"{_WORKFLOWS}/"
# What reading a file the repository wrote can raise: a path through a symlink, a file that
# cannot be opened, bytes that are not UTF-8 (a `ValueError`), a settings shape the engine
# refuses, and JSON nested past the parser's depth, which `json` answers with `RecursionError`.
_UNREADABLE = (PathEscape, OSError, ValueError, EntriesError, RecursionError)


@dataclass(frozen=True)
class ProbeContext:
    root: Path
    config: Config
    window: int  # how many commits `commit-types` reads


@dataclass(frozen=True)
class Looked:
    where: tuple[str, ...] = ()  # what was found
    unread: tuple[str, ...] = ()  # what could not be looked at


@dataclass(frozen=True)
class Probe:
    id: str
    principle: int | None
    severity: Severity
    remedy: str
    run: Callable[[ProbeContext], Looked]


def _git(context: ProbeContext, *args: str, answers: tuple[int, ...] = (0,)) -> str | None:
    """Standard output, or `None` when git's exit is not one of `answers` (a timeout is -1)."""
    code, out = git_run(context.root, *args, timeout=QUERY_TIMEOUT_SECONDS)
    return out if code in answers else None


def _head(context: ProbeContext) -> str | None:
    """`HEAD`'s sha, `""` in a repository with no commit, `None` when git cannot answer."""
    out = _git(context, "rev-parse", "--verify", "--quiet", "HEAD", answers=(0, 1))
    return None if out is None else out.strip()


def _names(out: str) -> list[str]:
    """NUL-terminated names, the empty tail dropped."""
    return [name for name in out.split("\0") if name]


def _todo_markers(context: ProbeContext) -> Looked:
    """Files under the code roots that carry a marker as a word. `-z` so a name git would quote
    is never read as the quoted form."""
    roots = [
        path.relative_to(context.root).as_posix()
        for path in contained_roots(context.root, context.config)
    ]
    if not roots:
        return Looked()
    out = _git(
        context, "grep", "-I", "-l", "-z", "-w", "-E", _MARKERS, "--", *roots, answers=(0, 1)
    )
    if out is None:
        return Looked(unread=("git grep",))
    return Looked(tuple(sorted(_names(out))))


def _tracked_env(context: ProbeContext) -> Looked:
    out = _git(context, "ls-files", "-z")
    if out is None:
        return Looked(unread=("git ls-files",))
    return Looked(
        tuple(
            sorted(
                name
                for name in _names(out)
                if (base := PurePosixPath(name).name) == ".env"
                or (base.startswith(".env.") and not base.endswith(_ENV_KEEP))
            )
        )
    )


def _memory_history(context: ProbeContext) -> Looked:
    if context.config.memory.mode == "in-repo":
        return Looked()  # the store is meant to be committed
    # Every ref, not `HEAD`'s history: notes committed on one branch are readable from a clone
    # checked out on an orphan one. With no commit anywhere git answers 0 and prints nothing.
    store = context.config.paths.memory
    out = _git(context, "log", "--all", "--format=%H", "-1", "--", store)
    if out is None:
        return Looked(unread=("git log",))
    return Looked((store,) if out.strip() else ())


def _foreign_hooks(context: ProbeContext) -> Looked:
    """Settings files of the selected harnesses that hold a hook entry without Keelline's
    marker. The engine's own shape check runs first, and every way repository content can make
    reading fail is "could not look"."""
    from keelline.harnesses import select

    harnesses, _ = select(context.config.keelline.agents)
    found: list[str] = []
    unread: list[str] = []
    for relative in sorted({s for h in harnesses for s in h.settings}):
        try:
            path = contained(context.root, relative)
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            owned_ids(text)  # raises EntriesError for a shape `doctor` would name
            hooks = json.loads(text).get("hooks", {}) if text.strip() else {}
        except _UNREADABLE:
            unread.append(relative)
            continue
        entries = [
            e for groups in hooks.values() for group in groups for e in group.get("hooks", [])
        ]
        if any(
            not isinstance(e.get("command"), str) or marker_id(e["command"]) is None
            for e in entries
        ):
            found.append(relative)
    return Looked(tuple(found), tuple(unread))


def _foreign_workflows(context: ProbeContext) -> Looked:
    from keelline.project.api import CI_WORKFLOW

    own = PurePosixPath(CI_WORKFLOW).name
    try:
        directory = contained(context.root, _WORKFLOWS)
        names = sorted(
            p.name
            for pattern in ("*.yml", "*.yaml")
            for p in directory.glob(pattern)
            if p.name != own
        )
    except (PathEscape, OSError):
        return Looked(unread=(_WORKFLOWS,))
    return Looked(tuple(f"{_WORKFLOWS}/{name}" for name in names))


# GitHub does not load a code-owners file of 3 MB or more. Decimal megabytes: of the two
# readings it is the smaller bound, so a file between them is read as unowned, the side that
# warns.
CODEOWNERS_MAX_BYTES = 3_000_000


def _glob(pattern: str, name: str) -> bool:
    """One path component against one pattern component: `*` is any run of characters and `?`
    is one, and everything else is itself.

    No regex, and that is the point: a run of `*` compiled one `[^/]*` each backtracks
    exponentially, and the pattern is the repository's. This walk keeps one resumption point,
    the last `*`, so it takes at most `len(pattern) * len(name)` steps whatever the pattern.
    """
    p = n = 0
    star, resume = -1, 0
    while n < len(name):
        if p < len(pattern) and pattern[p] in ("?", name[n]):
            p, n = p + 1, n + 1
        elif p < len(pattern) and pattern[p] == "*":
            star, resume, p = p, n, p + 1
        elif star >= 0:
            resume += 1
            p, n = star + 1, resume
        else:
            return False
    return pattern[p:].strip("*") == ""


def _components(pattern: tuple[str, ...], path: tuple[str, ...]) -> bool:
    """Whether `pattern`'s components match `path`'s, whole. `**` as a whole component is zero
    or more components, and one or more when it is the last: `a/**` is everything inside `a`,
    never `a`.

    A table rather than a recursion, filled from the pattern's end: `ahead[j]` says whether
    the rest of the pattern matches `path[j:]`. Adjacent `**` are one `**`, and a pattern with
    more other components than the path has cannot match, so the table is at most a few rows
    whatever the repository wrote.
    """
    pattern = tuple(
        part for i, part in enumerate(pattern) if part != "**" or pattern[i - 1 : i] != ("**",)
    )
    if sum(part != "**" for part in pattern) > len(path):
        return False
    end = len(path)
    ahead = [j == end for j in range(end + 1)]
    for i in range(len(pattern) - 1, -1, -1):
        if pattern[i] == "**":
            least = 1 if i == len(pattern) - 1 else 0
            ahead = [any(ahead[j + least :]) for j in range(end + 1)]
        else:
            ahead = [
                j < end and _glob(pattern[i], path[j]) and ahead[j + 1] for j in range(end + 1)
            ]
    return ahead[0]


def _owns(text: str, path: str) -> bool:
    """Whether the CODEOWNERS pattern `text` matches the file `path`, as GitHub reads it.

    The grammar is gitignore's without `!` and `[]`, which GitHub does not support: a pattern
    with no `/` but a trailing one matches at any depth, and any other is rooted. `**` is
    special only as a whole component; any other run of `*` is one `*`. A pattern matching a
    directory owns everything below it, and a trailing `/` makes it directory-only, so it never
    owns a file of that name.

    One rule is GitHub's and not git's: a last component of exactly `*` matches the directory's
    own files and nothing nested (GitHub's documentation: `docs/*` owns `docs/getting-started.md`
    and not `docs/build-app/troubleshooting.md`), where gitignore would match the directory
    `docs/build-app` and everything below it.
    """
    directory = text.endswith("/")
    anchored = text.startswith("/") or "/" in text.rstrip("/")
    parts = tuple(text.strip("/").split("/"))
    if not anchored:
        parts = ("**", *parts)
    names = tuple(path.split("/"))
    if not directory and _components(parts, names):
        return True
    if parts[-1] == "*":
        return False  # direct children only
    return any(_components(parts, names[:depth]) for depth in range(1, len(names)))


def _exact_file(path: Path) -> bool:
    """A file under exactly this name: a case-folding filesystem answers `is_file()` for
    `codeowners` when asked for `CODEOWNERS`, and GitHub reads only the exact name."""
    return path.is_file() and path.name in os.listdir(path.parent)


def _codeowners(context: ProbeContext) -> Looked:
    """Whether the line governing Keelline's workflow names an owner, read as GitHub reads it:
    the first code-owners file that exists under its exact name, and the last matching line in
    it. A line with a pattern and no owner leaves the path unowned."""
    from keelline.project.api import CI_WORKFLOW

    if context.config.ci.mode == "none":
        return Looked()  # Keelline renders no workflow to protect
    for relative in _CODEOWNERS:
        try:
            path = contained(context.root, relative)
            if not _exact_file(path):
                continue
            if path.stat().st_size >= CODEOWNERS_MAX_BYTES:
                return Looked((_UNOWNED,))  # GitHub does not load it
            text = path.read_text(encoding="utf-8")
        except (PathEscape, OSError, ValueError):
            return Looked(unread=(relative,))
        owners: list[str] = []
        for line in text.split("\n"):
            words = line.split("#", 1)[0].split()
            # GitHub skips a line with an owner that is neither `@user`, `@org/team` nor an
            # email address, so such a line decides nothing.
            if not words or not all("@" in word for word in words[1:]):
                continue
            if _owns(words[0], CI_WORKFLOW):
                owners = words[1:]
        return Looked(() if owners else (_UNOWNED,))
    return Looked((_UNOWNED,))


def _commit_types(context: ProbeContext) -> Looked:
    """Shas of the last `window` commits whose subject's type is outside the vocabulary. The
    records are NUL-delimited and paired by position, as the commit gate reads them: a subject
    may carry any byte but NUL, and nothing from one lands in `where`."""
    head = _head(context)
    if head is None:
        return Looked(unread=("git rev-parse",))
    if not head:
        return Looked()  # no commit yet
    out = _git(context, "log", "--no-merges", "-z", f"-n{context.window}", "--format=%H%x00%s")
    if out is None:
        return Looked(unread=("git log",))
    fields = out.split("\0")
    allowed = set(context.config.commit_messages.types)
    return Looked(
        tuple(
            fields[i]
            for i in range(0, len(fields) - 1, 2)
            if (m := _SUBJECT.match(fields[i + 1])) is None or m.group(1) not in allowed
        )
    )


PROBES: tuple[Probe, ...] = (
    Probe(
        "todo-markers",
        1,
        Severity.ADVICE,
        "file each marker that is a real defect with `keelline bugs new`, and delete the rest",
        _todo_markers,
    ),
    Probe(
        "tracked-env",
        None,
        Severity.WARNING,
        "remove the file from the index with `git rm --cached`, and rotate what it held",
        _tracked_env,
    ),
    Probe(
        "memory-history",
        8,
        Severity.WARNING,
        "notes committed to history stay readable in every clone; keep the store out of git",
        _memory_history,
    ),
    Probe(
        "foreign-hooks",
        5,
        Severity.ADVICE,
        "committed hooks run without a trust prompt in non-interactive sessions; keep only those "
        "you would run on every clone",
        _foreign_hooks,
    ),
    Probe(
        "foreign-workflows",
        None,
        Severity.ADVICE,
        "Keelline's workflow runs beside these; nothing needs changing unless one repeats a gate",
        _foreign_workflows,
    ),
    Probe(
        "codeowners",
        7,
        Severity.WARNING,
        "add a CODEOWNERS line covering /.github/ and require code-owner review on the gate "
        "branch: a pull request can otherwise rewrite the workflow that judges it",
        _codeowners,
    ),
    Probe(
        "commit-types",
        None,
        Severity.ADVICE,
        "write subjects as `<type>(<area>): <intent>`, with a type from [commit_messages] types",
        _commit_types,
    ),
)


def _could_not_look(probe: str, principle: int | None, unread: tuple[str, ...]) -> Item:
    return item(probe, COULD_NOT_LOOK, principle, Severity.WARNING, COULD_NOT_LOOK_REMEDY, unread)


def _profile_items(context: ProbeContext) -> list[Item]:
    """One item per failed check of the configured profile, at the check's own level.

    An empty `[keelline] profile` is no profile and runs nothing. A name this build does not
    ship is one warning and the rest of the inventory still runs; a shipped profile that does
    not parse stays `ProfileError`, because that is a defect in the build. A `tracked` check git
    gave no answer for is "could not look", never an untracked file.
    """
    name = context.config.keelline.profile
    if not name:
        return []
    from keelline import profiles

    shipped = profiles.shipped()
    if name not in shipped:
        remedy = PROFILE_NOT_SHIPPED_REMEDY.format(shipped=", ".join(shipped) or "none")
        return [
            item(
                PROFILE, PROFILE_NOT_SHIPPED, None, Severity.WARNING, remedy, ["[keelline] profile"]
            )
        ]
    items: list[Item] = []
    unanswered: dict[str, None] = {}
    for outcome in profiles.evaluate(profiles.load_profile(name), context.root):
        check = outcome.check
        if outcome.located:
            items.append(
                item(PROFILE, check.id, None, check.level, check.remedy, outcome.located, count=1)
            )
        unanswered.update(dict.fromkeys(outcome.unanswered))
    if unanswered:
        items.append(_could_not_look(PROFILE, None, tuple(unanswered)))
    return items


def run_probes(context: ProbeContext) -> list[Item]:
    """Every probe's items in `PROBES` order, then the profile's: per probe, what it found (the
    probe's id is the rule) and one `could-not-look` item for what it could not read."""
    items: list[Item] = []
    for probe in PROBES:
        looked = probe.run(context)
        if looked.where:
            items.append(
                item(
                    probe.id,
                    probe.id,
                    principle=probe.principle,
                    severity=probe.severity,
                    remedy=probe.remedy,
                    where=looked.where,
                )
            )
        if looked.unread:
            items.append(_could_not_look(probe.id, probe.principle, looked.unread))
    return items + _profile_items(context)
