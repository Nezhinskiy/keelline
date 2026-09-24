"""Refuse a write or removal git would never show, at a place a committed `[paths]` value chose:
one guard for `init`, `upgrade` and `uninstall`.

A managed region is inserted into whatever file its `[paths]` key names, recorded or not, and a
whole file is overwritten or removed while its bytes are the ones a record states. Both the
`[paths]` value and the record are committed, and the promise that makes that acceptable is that
the diff shows the result. For a file git ignores it does not: a pulled commit setting
`agents_md = ".env"` had `upgrade` report `region_update .env (refreshed)` and append the region
to a git-ignored `.env`, and `git status` showed only the manifest. With a record carrying the
digest of a predictable ignored file (a tool-generated marker), the same commit had `uninstall`
delete it or `upgrade` overwrite it. Nothing git ignores can be given back by git either.

**The rule is exactly three conditions, and a planned write or removal is refused only when all
three hold.** Its file exists: creating a file changes nothing that was there, and removing one
that is not there removes nothing. Git ignores it. And its place was chosen by a `[paths]` value,
that is, it is not a place this build could put that artifact under the preset's own paths
(`_preset_places`). A fixed name (`CLAUDE.md`, `keelline.toml`, `.gitignore`, the workflow, a
harness's rule) and a preset-default place are never refused: no repository value chose them, and
a person may well keep `CLAUDE.md` in a global excludes file or `keelline.toml` in
`.git/info/exclude` on purpose. A first version refused every ignored target, which refused those
setups outright and left `uninstall` no way to take back a `CLAUDE.md` Keelline wrote there. The
retirement a record can steer only ever reaches a target `could_write` lists, and those beyond the
preset's are `[paths]` values, so the `.env` case and the forged-record case stay refused.

One `git check-ignore`, before anything is written, dry run included; the refusal names each file
through `scaffold.printable`, the bound every report prints targets through.

**Ignored means what git would hide.** `check-ignore` consults the index, so a tracked file that
happens to match an ignore pattern is not ignored here: git shows every change to it. That is why
this is not `--no-index`, which the documentation lanes use to ask about patterns alone.

**`LOCAL_ARTIFACTS` is exempt**: `[artifacts] local` asks for exactly that directory, which the
footprint's ignore block keeps out of git on purpose.

**No repository, no guard.** Outside a git work tree, or with no `git` to ask, there is no diff
for a change to hide from, and every write still goes through `contained()` and the `O_NOFOLLOW`
walk. Inside one, a `check-ignore` that answers neither "some matched" nor "none matched" is a
refusal too, because a guard that cannot answer must not read as a pass.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from keelline.config.loader import preset_defaults
from keelline.config.schema import Config
from keelline.errors import Refusal
from keelline.gitenv import git_run
from keelline.project.templates import project_templates
from keelline.release.api import Resolution
from keelline.scaffold import LOCAL_ARTIFACTS, Action, Plan, Verb, printable

# Fixed text around `names`, which is each file through `printable`: a `[paths]` value inside the
# path grammar, or the artifact's id.
IGNORED = (
    "git ignores {count} file(s) this run would write or remove, at a place a [paths] value in "
    "keelline.toml chose ({names}), so the change would never show in a diff and git could not "
    "give it back; nothing was written. Point that [paths] key at a path git does not ignore, "
    "or take it out to use the preset's place, then run the command again"
)
IGNORED_REMOVING = (
    "git ignores {count} file(s) uninstall would remove or rewrite, at a place a [paths] value "
    "in keelline.toml chose ({names}), so what it did there would never show in a diff and git "
    "could not give it back; nothing was removed. Take Keelline's part out of them by hand, or "
    "take that [paths] key out of keelline.toml: uninstall then leaves those files where they "
    "are and lists them"
)
UNANSWERED = (
    "git could not say whether the files this run would write or remove are ignored, so nothing "
    "was written; run it again once `git check-ignore` works in this repository"
)


def _preset_places(root: Path, config: Config) -> Mapping[str, frozenset[str]]:
    """Every place this build could put each artifact under the preset's own `[paths]`.

    The same `project_templates` call every command makes, with `config.paths` replaced by the
    preset's defaults, so fixed names come out as themselves and every `[paths]`-built target as
    the preset puts it. A target outside what this answers for its id was chosen by a `[paths]`
    value in `keelline.toml`.
    """
    defaults = preset_defaults(config.project.name, preset=config.keelline.preset).paths
    placed = replace(config, paths=defaults)
    prepared = project_templates(
        root, placed, resolution=Resolution(None, True), document="", adopted=True
    )
    return prepared.could_write


def refuse_ignored(root: Path, config: Config, *plans: Plan, removing: bool = False) -> None:
    """Refuse when git ignores an existing file a write or removal in `plans` targets at a place
    a `[paths]` value chose; `removing` picks `uninstall`'s remedy."""
    places = _preset_places(root, config)
    chosen: dict[str, Action] = {}
    for planned in plans:
        for action in planned.actions:
            if action.verb is Verb.SKIP_MODIFIED:
                continue
            target = action.target
            if target.startswith(f"{LOCAL_ARTIFACTS}/"):
                continue
            if target in places.get(action.artifact_id, frozenset()):
                continue
            if os.path.lexists(root / target):
                chosen.setdefault(target, action)
    if not chosen:
        return
    # `--stdin -z`: the paths go in NUL-separated and never as arguments, so none is read as an
    # option, and come back unquoted, so the answer compares with what was asked.
    code, out = git_run(root, "check-ignore", "--stdin", "-z", stdin="\0".join(sorted(chosen)))
    if code == 1:
        return
    if code == 0:
        ignored = sorted({name for name in out.split("\0") if name} & set(chosen))
        if ignored:
            names = ", ".join(sorted({printable(chosen[target]) for target in ignored}))
            text = IGNORED_REMOVING if removing else IGNORED
            raise Refusal(text.format(count=len(ignored), names=names))
        return
    if git_run(root, "rev-parse", "--is-inside-work-tree")[0] == 0:
        raise Refusal(UNANSWERED)
