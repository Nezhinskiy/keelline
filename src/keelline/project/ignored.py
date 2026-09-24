"""Refuse a write or removal git would never show: one guard for `init`, `upgrade` and `uninstall`.

A managed region is inserted into whatever file its `[paths]` key names, recorded or not, and a
whole file is overwritten or removed while its bytes are the ones a record states. Both the
`[paths]` value and the record are committed, and the promise that makes that acceptable is that
the diff shows the result. For a file git ignores it does not: a pulled commit setting
`agents_md = ".env"` had `upgrade` report `region_update .env (refreshed)` and append the region
to a git-ignored `.env`, and `git status` showed only the manifest. With a record carrying the
digest of a predictable ignored file (a tool-generated marker), the same commit had `uninstall`
delete it or `upgrade` overwrite it. Nothing git ignores can be given back by git either.

So every planned write and removal is put to one `git check-ignore` before anything is written,
dry run included, and one it reports refuses the whole run. The refusal is fixed text and a
count: the targets come from committed values, so which of them matched is never printed.

**Ignored means what git would hide.** `check-ignore` consults the index, so a tracked file that
happens to match an ignore pattern is not ignored here: git shows every change to it. That is why
this is not `--no-index`, which the documentation lanes use to ask about patterns alone.

**Two exemptions, both Keelline's own.** An `[artifacts] local` artifact lives under
`LOCAL_ARTIFACTS`, which the footprint's ignore block keeps out of git on purpose; putting it
there is what the setting asks for. And the ledgers under `.keelline/` are not plan targets at all.

**No repository, no guard.** Outside a git work tree, or with no `git` to ask, there is no diff
for a change to hide from, and every write still goes through `contained()` and the `O_NOFOLLOW`
walk. Inside one, a `check-ignore` that answers neither "some matched" nor "none matched" is a
refusal too, because a guard that cannot answer must not read as a pass.
"""

from __future__ import annotations

from pathlib import Path

from keelline.errors import Refusal
from keelline.gitenv import git_run
from keelline.scaffold import LOCAL_ARTIFACTS, Plan

IGNORED = (
    "{count} file(s) this run would write or remove are ignored by git, so the change would never "
    "show in a diff and git could not give it back; nothing was written. A [paths] value in "
    "keelline.toml, or an ignore rule, puts an artifact on an ignored path: point the key at a "
    "path git does not ignore, or list the artifact in [artifacts] local to keep it out of git "
    "on purpose"
)
UNANSWERED = (
    "git could not say whether the files this run would write or remove are ignored, so nothing "
    "was written; run it again once `git check-ignore` works in this repository"
)


def refuse_ignored(root: Path, *plans: Plan) -> None:
    """Refuse when git ignores any file a write or removal in `plans` targets."""
    targets = sorted(
        {
            target
            for planned in plans
            for target in planned.writes
            if not target.startswith(f"{LOCAL_ARTIFACTS}/")
        }
    )
    if not targets:
        return
    # `--stdin -z`: the paths go in NUL-separated and never as arguments, so none is read as an
    # option, and come back unquoted, so the answer compares with what was asked.
    code, out = git_run(root, "check-ignore", "--stdin", "-z", stdin="\0".join(targets))
    if code == 1:
        return
    if code == 0:
        ignored = {name for name in out.split("\0") if name} & set(targets)
        if ignored:
            raise Refusal(IGNORED.format(count=len(ignored)))
        return
    if git_run(root, "rev-parse", "--is-inside-work-tree")[0] == 0:
        raise Refusal(UNANSWERED)
