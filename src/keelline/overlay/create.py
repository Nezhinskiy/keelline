"""Create the owner's private overlay, and make an instance theirs.

Two sources, one result. `--template` asks GitHub to generate a private repository from the
public template and clone it; `--local` renders `templates/overlay/` here through the scaffold
engine and touches no network. A template and not a fork (D1): a fork's visibility is bound to
the upstream network and cannot be made private, and an overlay that is not private is the one
outcome this whole area exists to prevent.

`init_instance` is what makes a generated repository *this owner's*: the plugin and marketplace
names carry their account, so two overlays installed into one harness never collide, and the
commit-time secret scan is installed. Neither step is destructive and both are idempotent —
`gh` may give up on the clone with the repository already created (§6.1), so a second run is the
ordinary case rather than the exception.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from keelline import fsops
from keelline.config.loader import preset_defaults
from keelline.errors import Failure, Refusal
from keelline.overlay.identity import require_overlay, segment
from keelline.overlay.layout import (
    CODEX_PLUGIN_MANIFEST,
    MARKETPLACE_MANIFEST,
    OVERLAY_FILES,
    PLUGIN_MANIFEST,
)
from keelline.overlay.runner import NOT_FOUND, TIMED_OUT, Completed, Runner
from keelline.overlay.template import templates
from keelline.scaffold import Manifest, apply, digest, plan

Source = Literal["template", "local"]
TEMPLATE_REPOSITORY = "keelline-overlay-template"
# The directory whose presence says a generated repository actually arrived — the exact probe
# Findings → S6 used, and the one thing a repository created from this template always carries.
# Deliberately weaker than `identity.overlay_fault`, and `identity`'s own docstring says why:
# this one answers "did a tree arrive here", which is the question idempotence asks of a clone
# `gh` gave up on half way through.
PROBE = ".claude-plugin"
# How long to wait before the one retry, when `gh` says the repository exists and the clone
# brought nothing down. Findings → S6 did not reproduce that race in the one trial it ran, so
# this is carried on the strength of the design rather than of a measurement: generation is
# asynchronous on GitHub's side and one clean run cannot rule out a slow one.
RETRY_WAIT_SECONDS = 10
# The precondition `docs/cli.md` names and the command itself never did. `--template` generates
# from a repository on the owner's own account, and the maintainer action that would publish it
# has not shipped, so on nearly every account this source cannot work at all today. A failure
# here that does not say so sends the owner to `gh auth status` for a repository that was never
# there.
UNSHIPPED_TEMPLATE = (
    f"`--template` generates from <owner>/{TEMPLATE_REPOSITORY}, and nothing publishes that "
    f"repository yet — the maintainer action that will has not shipped — so this source works "
    f"only for an owner who created it by hand. `keelline overlay create --local` renders the "
    f"same tree here and makes no network call"
)
# The three manifests `init_instance` names after the owner. The Codex one was left out of the
# first draft, so the collision the suffix exists to prevent still happened on Codex: two
# owners' overlays under one Codex configuration were one plugin fighting itself, which is the
# exact wording `init_instance`'s own docstring gives as the rationale.
MANIFESTS = (PLUGIN_MANIFEST, MARKETPLACE_MANIFEST, CODEX_PLUGIN_MANIFEST)


@dataclass(frozen=True)
class Created:
    root: Path
    source: Source
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Initialised:
    renamed: tuple[str, ...]
    notes: tuple[str, ...]


def target_root(root: Path, owner: str, name: str) -> tuple[Path, str]:
    """Where `create(owner, name, root=root)` would put the overlay, and the folded owner.

    Nothing is created and nothing is asked of the network, which is the point: `setup
    --overlay create:<owner>/<name>` has to be able to refuse the *destination* — for lying
    inside the project root, say — before it runs `gh repo create` on somebody's account. The
    destination is knowable from the arguments alone, and it used to be computed only by the
    call that had already created the repository.

    Folded before it is validated, and `init_instance` folds the same way, because `SEGMENT` has
    a lowercase leading class and a mixed-case GitHub login is ordinary. Validating the raw
    value refused `--owner OctoCat` from this command while the other accepted it — one owner
    string with two answers, and the refusal said "is not one path segment" about a value that
    plainly is one. Folding is safe: GitHub logins are case-insensitive, and the folded value is
    what reaches the slug, the remote and the manifest suffix alike.
    """
    account = segment("owner", owner.strip().lower())
    segment("name", name)
    return root / name, account


def _populated(target: Path) -> bool:
    return (target / PROBE).is_dir()


def _render_locally(root: Path, name: str) -> Path:
    target = root / name
    # **Everything that can refuse runs before anything is created**, and the order is
    # load-bearing rather than tidy. `mkdirs_within` below creates `<name>/.claude-plugin`,
    # which is exactly `PROBE` — so a render that failed after it (`templates()` on a Keelline
    # installed without the tree, a manifest that will not parse, a refused path) would leave
    # behind the one directory that makes a later `overlay create --template` answer "already
    # exists and was left alone" and never create the repository at all. The idempotence rule
    # would silently swallow the real command. A refusal has to cost nothing on disk.
    #
    # `plan` reads and decides and writes nothing, and it is happy with a root that does not
    # exist yet: `Manifest.read` finds no file and every artifact reads as absent.
    planned = plan(target, preset_defaults(name), templates())
    # The engine writes through `fsops` and walks every component with `O_NOFOLLOW`, but it
    # cannot open a root that is not there yet. `mkdirs_within` creates a target's *parents*, so
    # the instance directory is asked for as the parent of the first file that goes into it —
    # through the same walk, rather than with the `Path.mkdir(parents=True)` this project does
    # not allow into a lane that puts files into a repository.
    fsops.mkdirs_within(root, f"{name}/{OVERLAY_FILES[0]}")
    apply(target, planned)
    return target


def create(
    owner: str,
    name: str,
    *,
    source: Source,
    root: Path,
    runner: Runner,
    wait: Callable[[float], None] = time.sleep,
) -> Created:
    """Create `root/<name>`, from the template repository or from the shipped tree."""
    # One spelling of "where this lands and what the owner is called", shared with the caller
    # that has to ask before it calls (`setup`'s `--overlay create:`); see `target_root`.
    _, account = target_root(root, owner, name)
    if not root.is_dir():
        # Both branches below start by opening this directory — the contained walk for the
        # local render, the subprocess `cwd` for the other — and a missing one is a mistyped
        # `--root`, which is a refusal a person can act on rather than an internal error.
        raise Refusal(f"{root} is not a directory; name one that exists with --root")
    if source == "local":
        return Created(
            _render_locally(root, name),
            source,
            ("rendered from the shipped template; no network call was made",),
        )
    return _from_template(account, name, root=root, runner=runner, wait=wait)


def _detail(done: Completed) -> str:
    """What a subprocess said about itself, in the order a reader wants it.

    `Completed` has carried `code` and `stderr` since this seam was written and this lane threw
    both away: with `gh` absent from `PATH`, every call answered `Completed(127, "", "gh could
    not be run: …")` and the failure below still said "GitHub did not confirm the repository
    exists; check `gh auth status`" — a cause that was not the cause, about a binary that was
    not there. The same idiom `setup.run` uses for its notes.
    """
    return done.stderr.strip() or done.stdout.strip() or f"exit {done.code}"


def _from_template(
    owner: str, name: str, *, root: Path, runner: Runner, wait: Callable[[float], None]
) -> Created:
    target = root / name
    if _populated(target):
        # §6.1 asks for idempotence in as many words: `gh` may give up on the clone with the
        # repository already created, so the second run finds a tree and must not re-create.
        return Created(target, "template", (f"{target} already exists and was left alone",))
    slug = f"{owner}/{name}"
    created = runner.run(
        [
            "gh",
            "repo",
            "create",
            slug,
            "--private",
            "--template",
            f"{owner}/{TEMPLATE_REPOSITORY}",
            "--clone",
        ],
        root,
    )
    if _populated(target):
        return Created(target, "template", (f"created {slug} from {TEMPLATE_REPOSITORY}",))
    if created.code in (NOT_FOUND, TIMED_OUT):
        # `gh` could not be launched at all, or hung until the seam gave up. Neither is a state
        # two further subprocesses and a ten-second wait can learn anything about: `gh repo
        # view` would ask the same absent binary a second question, get the same answer, and the
        # failure would then name GitHub for a fault that is this machine's. The global
        # constraints make `gh` optional — so this is a reported finding that names it.
        raise Failure(
            f"`gh repo create {slug} …` could not be run ({_detail(created)}), so nothing was "
            f"created and nothing was cloned. Install `gh` and authenticate it, or render the "
            f"overlay locally: {UNSHIPPED_TEMPLATE}"
        )
    if created.code != 0:
        # `gh` ran and declined. Its own stderr is the cause — a missing template repository, an
        # expired token, a name already taken — and it is quoted rather than replaced by a
        # guess. The clone is still retried below only when `gh` *succeeded* and nothing
        # arrived, which is the one shape the race can take.
        raise Failure(
            f"`gh repo create {slug} …` exited {created.code} ({_detail(created)}), so no tree "
            f"arrived at {target}. {UNSHIPPED_TEMPLATE}"
        )

    # `gh` reported success and nothing arrived. Which of the two failures it was decides whether
    # waiting can help, so ask before retrying: `gh repo view` printing the name back is the
    # evidence the repository exists and the clone raced its generation.
    view = runner.run(["gh", "repo", "view", slug, "--json", "name", "--jq", ".name"], root)
    raced = view.code == 0 and bool(view.stdout.strip())
    if raced:
        wait(RETRY_WAIT_SECONDS)
    # The clone is retried either way, and that is deliberate: `gh repo view` answering nothing
    # is not proof of absence — a rate limit or an expired token answers the same — and one fast
    # failure is cheaper than refusing to try.
    cloned = runner.run(["git", "clone", "--", f"git@github.com:{slug}.git", name], root)
    if _populated(target):
        return Created(target, "template", (f"cloned {slug} on the second attempt",))
    raise Failure(
        f"{slug} produced no tree at {target}: `gh repo create --clone` reported success and "
        f"left nothing, and the "
        + ("retried" if raced else "one further")
        + f" `git clone` exited {cloned.code} ({_detail(cloned)}). "
        + (
            "GitHub reports the repository exists, so generation may still be running — wait and "
            "clone it by hand"
            if raced
            else f"`gh repo view` did not confirm the repository exists ({_detail(view)}); "
            f"check `gh auth status`. {UNSHIPPED_TEMPLATE}"
        )
    )


def _suffixed(value: object, suffix: str) -> str | None:
    """The renamed value, or `None` when it is already suffixed or not a name at all."""
    if not isinstance(value, str) or not value or value.endswith(f"-{suffix}"):
        return None
    return f"{value}-{suffix}"


NOT_AN_OVERLAY = (
    "`keelline overlay init --root` must name an overlay. It rewrites the tree's plugin "
    "manifests and installs a commit hook there, so pointed at anything else -- a project, or "
    "the Keelline checkout itself -- it renames somebody else's manifests"
)


def init_instance(root: Path, owner: str, *, runner: Runner) -> Initialised:
    """Make a generated overlay this owner's: name it after them, and install the secret scan.

    §6.1 wants the suffix "so two overlays never collide" — a harness installs a plugin by the
    name in its manifest, so two owners' overlays under one configuration directory would be one
    plugin fighting itself. **All three manifests**, because the project ships a Codex half of
    everything else and `.codex-plugin/plugin.json` left unsuffixed is that collision still
    happening, one harness over. Each is rewritten through `fsops.write_within`: the overlay
    root *is* a root, so the contained walk applies and there is no carve-out to take.

    **Every rewrite is re-stamped into the scaffold ledger.** `create --local` renders these
    files through the engine, which records each one's digest; a rewrite behind the ledger's
    back makes the file read as hand-edited for ever after, so `overlay upgrade` reported
    `skip_modified .claude-plugin/plugin.json (hand-edited)` and never refreshed it again — for
    the one file carrying `keelline.requires`, the version-compatibility declaration the README
    advertises, and attributing to the owner an edit Keelline itself made. Re-stamping is the
    narrow answer of the two the review offered; rendering the suffix through the `Template`
    instead would put an owner-dependent value into the shipped tree, which every *other*
    consumer of that tree (`upgrade`'s hash rule, the release lane) would then have to know
    about. A `--template` clone carries no ledger at all, and gets no record written for it.

    A manifest that is *absent* is a note rather than a failure. An overlay generated before the
    Codex half shipped carries two of the three, and refusing to name the other two over it
    would make this command unusable on exactly the overlays that most need it; one that exists
    and cannot be read is still a failure, because that is a file saying something this command
    cannot act on.

    **Asked whether `root` is an overlay before anything is touched**, the way `upgrade` asks
    and `setup` asks twice. `--root` defaults to `.`, and run inside the Keelline checkout this
    renamed all three of its plugin manifests and installed a hook into it.
    """
    require_overlay(root, because=NOT_AN_OVERLAY)
    suffix = segment("owner", owner.strip().lower())
    ledger = Manifest.read(root)
    renamed: list[str] = []
    absent: list[str] = []
    notes: list[str] = []
    restamped = False
    for relative in MANIFESTS:
        if not (root / relative).is_file():
            absent.append(relative)
            continue
        written = _rename(root, relative, suffix)
        if written is None:
            continue
        renamed.append(relative)
        record = ledger.get(relative)
        if record is not None:
            ledger = ledger.with_record(replace(record, sha256=digest(written)))
            restamped = True
    if restamped:
        ledger.write(root)
    if renamed:
        notes.append(f"named this overlay after {suffix}: {', '.join(renamed)}")
    else:
        notes.append(f"the manifests already name {suffix}; nothing was renamed")
    if absent:
        notes.append(
            f"this overlay carries no {', '.join(absent)}, so there was nothing to name there; "
            f"`keelline overlay upgrade` adds what a newer template ships"
        )
    notes.append(_install_secret_scan(root, runner))
    return Initialised(tuple(renamed), tuple(notes))


def _rename(root: Path, relative: str, suffix: str) -> str | None:
    """The bytes written, or `None` when this manifest already named the owner.

    The text and not a boolean, because the caller re-stamps the scaffold ledger with exactly
    what went to disk — reading the file back to hash it would hash whatever is there now.
    """
    path = root / relative
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Failure(f"{relative} cannot be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise Failure(f"{relative} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise Failure(f"{relative} is not a JSON object")
    changed = False
    if (renamed := _suffixed(document.get("name"), suffix)) is not None:
        document["name"] = renamed
        changed = True
    # The marketplace's entries name the plugin they publish, so an entry left unsuffixed would
    # advertise a plugin whose manifest no longer answers to that name.
    entries = document.get("plugins")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and (name := _suffixed(entry.get("name"), suffix)):
                entry["name"] = name
                changed = True
    if not changed:
        return None
    body = json.dumps(document, indent=2) + "\n"
    fsops.write_within(root, relative, body)
    return body


def _install_secret_scan(root: Path, runner: Runner) -> str:
    """Install the commit-time secret scan, or say why it is not installed.

    §6.4 runs gitleaks twice and this is one of the two; the other is the push workflow the
    template ships, which is what makes `--no-verify` not the last word. A missing `pre-commit`
    is a reported finding, never a traceback.
    """
    done: Completed = runner.run(["pre-commit", "install"], root)
    if done.code == 0:
        return "installed the commit-time secret scan with `pre-commit install`"
    detail = done.stderr.strip() or done.stdout.strip() or f"exit {done.code}"
    return (
        f"`pre-commit install` did not run ({detail}), so the commit-time secret scan is not "
        f"installed; install pre-commit and run it in {root}. The push-time scan still runs"
    )
