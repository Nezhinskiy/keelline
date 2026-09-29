"""The block `attach` keeps in the repository's `info/exclude`, and the one question it is built on.

`attach` puts machine-local files into a checkout: the link tree under `paths.memory`, the Codex
rule copies under `.codex/rules/` and `.claude/settings.local.json`. None of them is anything a
collaborator should see, and none was ignored, so every `git status` listed them and a
`git add -A` committed the owner's personal links and rules. `.gitignore` is the wrong place to
hide them: it is committed, so the hiding would itself be a change every collaborator gets, and
`init` already owns the one region `attach` may keep there. `info/exclude` is the repository's own
exclude file, which no clone carries, and git resolves it in the common directory, so one block
covers the main checkout and every worktree.

**Only what git does not hide already.** The question is `git check-ignore --stdin`, and
deliberately **without** `--no-index`: "ignored" here means what `git status` would hide, and a
tracked file that matches a pattern is not hidden — the rule `project/ignored.py` states for the
same command. A checkout that keeps the whole footprint out of git already, through its own
`info/exclude` or a global excludes file, gets no block at all, and `.gitignore`'s region is asked
about the same way (`write.attach`), so such a checkout is not touched.

Security ruling, in the order the template asks for it. **Preconditions**: every candidate path is
computed by stayfixed — `paths.memory` and each `memory.groups` entry are repository-authored, but
each candidate is held inside the project by `config.paths.contained` before it is asked about,
and a name no exclude line can hold as one line is left out, so it stays visible rather than being
hidden by a line the repository wrote: a line break, a NUL (git's reader ends the line there, so
the pattern would be a shorter path's), and every other character `str.splitlines` breaks at (a
reader that splits there would take one line for several). Of the characters left, git's
pattern syntax gives a meaning to `\\`, `*`, `?`, `[` and a space (a trailing one is dropped), and
each is escaped, so a group named `*` hides that one link and not the directory. The block is read
back the way git reads it, at `\\n` alone. **Anchor**: git's own ignore evaluation in this
checkout, which is the only authority on what `git status` shows. **Write
target**: `info/exclude` as `git rev-parse --git-path` names it — `guards.git_path`, the resolver
`setup --git-hooks` uses — refused when it is a symlink, as `guards.githooks.install` refuses a
symlinked hook, and written with `fsops.write_atomically`, whose rename replaces the name rather
than writing through it. **Who must not be refused**: a checkout that already hides everything,
where `attach` changes nothing and so never needs the file at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from stayfixed import fsops
from stayfixed.config.paths import contained
from stayfixed.errors import Refusal
from stayfixed.gitenv import git_run
from stayfixed.guards.api import git_path
from stayfixed.scaffold import Style, drop, extract, upsert

# What `git rev-parse --git-path` is asked for, and the region's name in it: the block reads
# `# stayfixed:attach:begin` ... `# stayfixed:attach:end`.
EXCLUDE = "info/exclude"
EXCLUDE_REGION = "attach"
EXCLUDE_NOTE = "# stayfixed attach: this machine's links, rules and settings, not a collaborator's."
# The characters git's pattern syntax gives a meaning to inside a path, each escaped with a
# backslash so the line matches the one path it was written for. A space is escaped too: a
# trailing one is dropped by git unless it is.
_SPECIAL = frozenset("\\*?[ ")
UNANSWERED = (
    "git could not say which of the files `attach` places are already ignored, so nothing was "
    "written; run it again once `git check-ignore` works in this repository"
)
# The path is git's answer about this checkout's own git directory, not a value the repository
# chose, so it prints.
LINKED = (
    "{path} is a symlink, and `attach` writes the repository's exclude file only as a real file; "
    "nothing was written. Replace the link with the file it points at and run it again"
)
UNREADABLE = "{path} cannot be read as text ({reason}), so nothing was written"


@dataclass(frozen=True)
class ExcludeWrite:
    """The whole new text of the exclude file, computed before `attach`'s first write."""

    path: Path
    text: str


def unignored(root: Path, relatives: Sequence[str]) -> tuple[str, ...]:
    """The members of `relatives` git would still show, in their given order.

    `--stdin -z`: the paths go in NUL-separated and never as arguments, so none is read as an
    option, and come back unquoted, so the answer compares with what was asked. Exit 1 is "none
    matched", an answer; anything but 0 and 1 is no answer, and a refusal, because treating it
    as "nothing is ignored" would write, and treating it as "everything is" would hide nothing.
    """
    if not relatives:
        return ()
    code, out = git_run(root, "check-ignore", "--stdin", "-z", stdin="\0".join(relatives))
    if code == 1:
        return tuple(relatives)
    if code != 0:
        raise Refusal(UNANSWERED)
    hidden = {name for name in out.split("\0") if name}
    return tuple(relative for relative in relatives if relative not in hidden)


def pattern(relative: str) -> str | None:
    """The one exclude line matching exactly `relative` from the checkout's top, or `None`.

    Anchored with a leading `/`, which also means no line starts with `!` or `#`. `None` for a
    path no single line can hold: a line break, a NUL, at which git's reader ends the line, or
    any other character `str.splitlines` breaks at, which a reader splitting there would take
    for the end of a line and the start of another. That path is left visible.
    """
    if relative.splitlines() != [relative] or "\0" in relative:
        return None
    return "/" + "".join(f"\\{char}" if char in _SPECIAL else char for char in relative)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else ""
    except UnicodeDecodeError:
        raise Refusal(UNREADABLE.format(path=path, reason="not UTF-8")) from None
    except OSError as exc:
        raise Refusal(UNREADABLE.format(path=path, reason=fsops.said(exc))) from exc


def _patterns(body: str | None) -> list[str]:
    """The pattern lines of an earlier block, split where git splits them: at `\\n` alone, with
    the one `\\r` before it dropped, as git drops it.

    Never `str.splitlines`, which also breaks at U+2028, `\\x85`, a form feed and five more: a
    line an earlier stayfixed wrote with one of those in it came back as several, and a `!.env`
    among them un-hid a file the owner's own excludes hide (`gitenv.answer_lines` gives the same
    rule for git's answers).
    """
    lines = (line.removesuffix("\r") for line in (body or "").split("\n"))
    return [line for line in lines if line and not line.startswith("#")]


def planned_block(root: Path, relatives: Sequence[str]) -> ExcludeWrite | None:
    """The exclude file with this attach's block, or `None` when nothing needs hiding.

    Asked above every write: containment, `check-ignore`, the resolution of the file and its
    symlink refusal all raise before `attach` has touched anything. The block is the union of
    what an earlier attach put there and what this one still finds visible, because a path an
    earlier block hides reads as ignored now, and a block rebuilt from this run alone would drop
    it and show it again.
    """
    for relative in relatives:
        # `allow_final_symlink`: the link tree's entries are symlinks by design.
        contained(root, relative, allow_final_symlink=True)
    lines = [line for line in map(pattern, unignored(root, relatives)) if line is not None]
    if not lines:
        return None
    path = git_path(root, EXCLUDE, "exclude file")
    if path.is_symlink():
        raise Refusal(LINKED.format(path=path))
    current = _read(path)
    kept = _patterns(extract(current, EXCLUDE_REGION, Style.HASH))
    body = "\n".join([EXCLUDE_NOTE, *kept, *(line for line in lines if line not in kept)])
    updated = upsert(current, EXCLUDE_REGION, body, Style.HASH)
    return None if updated == current else ExcludeWrite(path, updated)


def withdrawn_block(root: Path) -> ExcludeWrite | None:
    """The exclude file with this attach's block taken out, or `None` when there is none.

    Asked above `detach`'s first withdrawal, for the reason `_ignore_region_remainder` is: a
    block opened twice is a `RegionError` knowable at the start. A symlinked file is left alone
    rather than refused, because `attach` never writes through one, so a block behind a link is
    not one this command put there.
    """
    path = git_path(root, EXCLUDE, "exclude file")
    if path.is_symlink() or not path.is_file():
        return None
    current = _read(path)
    remaining = drop(current, EXCLUDE_REGION, Style.HASH)
    return None if remaining == current else ExcludeWrite(path, remaining)


def write(planned: ExcludeWrite) -> None:
    """Replace the exclude file in one rename; the path is git's answer, not a configured one."""
    fsops.write_atomically(planned.path, planned.text)
