"""Publish the overlay template repository from the owner's checkout (§5.9, §6.1, DC6).

Render `templates/overlay/` into a scratch directory, strip the scaffold ledger (a repository
generated from a template carries none, and publishing one would make every generated overlay
read as hand-edited to `overlay upgrade`), make sure the repository exists, is public and is
marked as a template, clone it, replace its tree with the render, commit, and — only with
`yes` — push. Everything that leaves this process goes through `Runner`, so a test asserts the
argv and never reaches GitHub.

**`yes` gates everything outward-facing**, which is three acts and not one: the repository's
creation, its template flag, and the push. Without it the command renders, asks `gh` what
exists — a read — and reports what it would create, mark and push. That is the dry run; there
is no separate `--dry-run` flag, because a second way to say the same thing is a second thing
to get wrong. The first draft of this ran `gh repo create --public` before the gate, so the
documented dry run created a public repository on the owner's account.

**It runs from the owner's authenticated checkout by design.** §5.9: the public repository's
CI holds no credential that can write a second repository, so this is not a workflow and never
becomes one. `gh` decides the protocol and carries the token; this module only names the argv.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import keelline
from keelline import fsops
from keelline.errors import Failure, Refusal
from keelline.overlay.create import TEMPLATE_REPOSITORY, _render_locally
from keelline.overlay.identity import segment
from keelline.overlay.layout import OVERLAY_FILES
from keelline.runner import NOT_FOUND, TIMED_OUT, Completed, Runner
from keelline.scaffold import MANIFEST_PATH

# `TEMPLATE_REPOSITORY` stays defined in `create.py` — `publish` imports `_render_locally` from
# there, so that is the direction without a cycle — and is named here so a caller of this module
# has one place to read. `__all__` because mypy's re-export rule wants the intent said out loud.
__all__ = ["DESCRIPTION", "TEMPLATE_REPOSITORY", "Existing", "Published", "publish_template"]

DESCRIPTION = "The template a Keelline private overlay is generated from"
# The branch a repository this command just created has: `gh repo create` with no push leaves
# no branch to read, so there is nothing to ask and the platform's own default is what a first
# push names. An existing repository answers for itself through `Existing.default_branch`.
DEFAULT_BRANCH = "main"


@dataclass(frozen=True)
class Published:
    repository: str
    changed: tuple[str, ...]
    pushed: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Existing:
    """What `gh repo view` says about the named repository, before anything is decided.

    Read once and passed to both the dry-run report and the ensure step, so the two cannot
    disagree about what is there — and so the read happens above the gate while every write
    happens below it.
    """

    exists: bool
    is_template: bool
    visibility: str
    default_branch: str


def _detail(done: Completed) -> str:
    return done.stderr.strip() or done.stdout.strip() or f"exit {done.code}"


def _gh(runner: Runner, argv: list[str], cwd: Path) -> Completed:
    done = runner.run(["gh", *argv], cwd)
    if done.code in (NOT_FOUND, TIMED_OUT):
        raise Failure(
            f"`gh {' '.join(argv[:2])} …` could not be run ({_detail(done)}); install and "
            f"authenticate gh"
        )
    return done


def _inspect_repository(runner: Runner, slug: str, cwd: Path) -> Existing:
    """Ask GitHub what is there. A read, and the only outward-facing call the gate does not
    cover — because reporting what `--yes` would do requires knowing what exists."""
    view = _gh(
        runner, ["repo", "view", slug, "--json", "isTemplate,visibility,defaultBranchRef"], cwd
    )
    if view.code != 0:
        return Existing(False, False, "", DEFAULT_BRANCH)
    try:
        document = json.loads(view.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise Failure(f"`gh repo view {slug}` did not answer with JSON: {exc}") from None
    if not isinstance(document, dict):
        raise Failure(f"`gh repo view {slug}` answered with JSON that is not an object")
    branch = document.get("defaultBranchRef")
    named = branch.get("name") if isinstance(branch, dict) else None
    return Existing(
        True,
        bool(document.get("isTemplate")),
        str(document.get("visibility") or ""),
        str(named or DEFAULT_BRANCH),
    )


def _not_public(slug: str, visibility: str) -> str:
    return (
        f"{slug} exists and is not public ({visibility.lower() or 'visibility unknown'}); a "
        f"template is generated from by other accounts only when it is public, and a "
        f"repository under this name that somebody made private is not one this command may "
        f"flip a flag on — publish under a different --name, or make that repository public "
        f"yourself first"
    )


def _dry_run_notes(existing: Existing, slug: str) -> list[str]:
    """What `--yes` would do, said before any of it is done."""
    if not existing.exists:
        return [f"would create {slug}, public, and mark it as a template"]
    if existing.visibility.upper() != "PUBLIC":
        return [f"{_not_public(slug, existing.visibility)} — so --yes would refuse here"]
    if not existing.is_template:
        return [f"would mark {slug} as a template repository"]
    return []


def _ensure_repository(
    runner: Runner, slug: str, cwd: Path, existing: Existing
) -> tuple[list[str], str]:
    """Create it public, or mark an existing public one — and refuse one that is not public.

    Returns the notes and the branch a push should name.
    """
    notes: list[str] = []
    if not existing.exists:
        created = _gh(
            runner, ["repo", "create", slug, "--public", "--description", DESCRIPTION], cwd
        )
        if created.code != 0:
            raise Failure(f"`gh repo create {slug}` exited {created.code} ({_detail(created)})")
        notes.append(f"created {slug}, public")
        is_template, default_branch = False, DEFAULT_BRANCH
    else:
        if existing.visibility.upper() != "PUBLIC":
            raise Refusal(_not_public(slug, existing.visibility))
        is_template, default_branch = existing.is_template, existing.default_branch
    if not is_template:
        marked = _gh(runner, ["repo", "edit", slug, "--template"], cwd)
        if marked.code != 0:
            raise Failure(
                f"`gh repo edit {slug} --template` exited {marked.code} ({_detail(marked)})"
            )
        notes.append(f"marked {slug} as a template repository")
    return notes, default_branch


def _render_tree(rendered: Path) -> tuple[str, ...]:
    """The shipped files the render actually left, in `OVERLAY_FILES` order."""
    return tuple(relative for relative in OVERLAY_FILES if (rendered / relative).is_file())


def _replace_tree(clone: Path, rendered: Path) -> None:
    """Every tracked file out, every rendered file in — through the contained walk.

    **The containment anchor is `clone`, and this process made it.** It is a directory under
    the `TemporaryDirectory` opened two frames up, named by this module and cloned into by
    `gh`; no argument, no configuration file and no repository chooses it, which is what makes
    "refuse anything outside it" a rule the party being contained cannot move. `.git` is the
    one thing left standing, because the clone's history is what the push carries.
    """
    for path in sorted(clone.rglob("*"), reverse=True):
        if ".git" in path.relative_to(clone).parts:
            continue
        relative = str(path.relative_to(clone))
        if path.is_file():
            fsops.remove_within(clone, relative)
        elif path.is_dir() and not any(path.iterdir()):
            fsops.rmdir_within(clone, relative)
    for relative in OVERLAY_FILES:
        fsops.write_within(clone, relative, (rendered / relative).read_text(encoding="utf-8"))


def publish_template(
    owner: str, *, name: str = TEMPLATE_REPOSITORY, yes: bool, runner: Runner
) -> Published:
    """Render the shipped overlay tree and publish it as `<owner>/<name>`."""
    # Folded before it is validated, exactly as `create.target_root` folds it and for the same
    # reason: `SEGMENT` has a lowercase leading class and a mixed-case GitHub login is ordinary.
    account = segment("owner", owner.strip().lower())
    segment("name", name)
    slug = f"{account}/{name}"
    with tempfile.TemporaryDirectory(prefix="keelline-publish-") as scratch_name:
        scratch = Path(scratch_name)
        rendered = _render_locally(scratch, "rendered")
        # The ledger is the scaffold engine's record of what `create --local` wrote here. A
        # repository generated from a template carries none (`init_instance`'s docstring), so
        # publishing one would make every generated overlay read as hand-edited to `overlay
        # upgrade` and never be refreshed again.
        fsops.remove_within(rendered, str(MANIFEST_PATH))
        fsops.rmdir_within(rendered, str(MANIFEST_PATH.parent))
        # Nothing outward-facing before the gate. Without `yes` the repository is only ASKED
        # about: what would be created or marked is reported, never done — a dry run that
        # created a public repository on the owner's account was the first draft's defect.
        existing = _inspect_repository(runner, slug, scratch)
        written = _render_tree(rendered)
        if not yes:
            notes = _dry_run_notes(existing, slug)
            if existing.exists and existing.visibility.upper() != "PUBLIC":
                return Published(slug, written, False, tuple(notes))
            notes.append(
                f"would push {len(written)} file(s) to {slug}; re-run with --yes to publish"
            )
            return Published(slug, written, False, tuple(notes))
        notes, default_branch = _ensure_repository(runner, slug, scratch, existing)
        # `gh repo clone`, not `git clone git@…`: it uses whichever protocol `gh` is
        # authenticated over, which is the premise the whole command rests on. A full clone,
        # not `--depth 1`: a shallow graft is not a history anyone wants pushed.
        cloned = runner.run(["gh", "repo", "clone", slug, "clone"], scratch)
        clone = scratch / "clone"
        if cloned.code != 0 or not clone.is_dir():
            raise Failure(f"`gh repo clone {slug}` exited {cloned.code} ({_detail(cloned)})")
        _replace_tree(clone, rendered)
        runner.run(["git", "-C", str(clone), "add", "-A"], clone)
        status = runner.run(["git", "-C", str(clone), "status", "--porcelain"], clone)
        changed = tuple(line[3:] for line in status.stdout.splitlines() if line.strip())
        if not changed:
            notes.append(f"{slug} already carries this Keelline's template; nothing to push")
            return Published(slug, (), False, tuple(notes))
        message = f"keelline overlay template {keelline.__version__}"
        committed = runner.run(["git", "-C", str(clone), "commit", "-q", "-m", message], clone)
        if committed.code != 0:
            raise Failure(f"committing the template exited {committed.code} ({_detail(committed)})")
        # `HEAD:refs/heads/<default>`: a freshly created repository has no branch to clone,
        # so a bare `push origin HEAD` would push whatever `init.defaultBranch` says.
        pushed = runner.run(
            ["git", "-C", str(clone), "push", "origin", f"HEAD:refs/heads/{default_branch}"], clone
        )
        if pushed.code != 0:
            raise Failure(f"`git push` to {slug} exited {pushed.code} ({_detail(pushed)})")
        notes.append(f"pushed {len(changed)} changed file(s) to {slug} as {message!r}")
    return Published(slug, changed, True, tuple(notes))
