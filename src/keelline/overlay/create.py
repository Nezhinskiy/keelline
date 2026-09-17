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
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from keelline import fsops
from keelline.config.loader import preset_defaults
from keelline.errors import Failure, Refusal
from keelline.overlay.layout import MARKETPLACE_MANIFEST, OVERLAY_FILES, PLUGIN_MANIFEST
from keelline.overlay.runner import Completed, Runner
from keelline.overlay.template import templates
from keelline.scaffold import apply, plan

SOURCES = ("template", "local")
TEMPLATE_REPOSITORY = "keelline-overlay-template"
# The directory whose presence says a generated repository actually arrived — the exact probe
# Findings → S6 used, and the one thing a repository created from this template always carries.
PROBE = ".claude-plugin"
# How long to wait before the one retry, when `gh` says the repository exists and the clone
# brought nothing down. Findings → S6 did not reproduce that race in the one trial it ran, so
# this is carried on the strength of the design rather than of a measurement: generation is
# asynchronous on GitHub's side and one clean run cannot rule out a slow one.
RETRY_WAIT_SECONDS = 10
# One path segment, and the same grammar `scaffold.engine.SOURCE_NAME` holds a profile to. A
# name becomes a directory, half a remote path and later a marketplace selector, so it is
# checked once here rather than at each of those; the leading class is what keeps a value shaped
# like an option (`-flag`) out of an option's position in an argv (§3).
SEGMENT = re.compile(r"^[a-z0-9][a-z0-9._-]*\Z")


@dataclass(frozen=True)
class Created:
    root: Path
    source: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Initialised:
    renamed: tuple[str, ...]
    notes: tuple[str, ...]


def _segment(label: str, value: str) -> str:
    if not SEGMENT.match(value):
        raise Refusal(
            f"{label} {value!r} is not one path segment matching {SEGMENT.pattern}; it becomes a "
            "directory name, half a remote path and a marketplace selector, so it is refused "
            "rather than quoted"
        )
    return value


def _populated(target: Path) -> bool:
    return (target / PROBE).is_dir()


def _render_locally(root: Path, name: str) -> Path:
    target = root / name
    # The engine writes through `fsops` and walks every component with `O_NOFOLLOW`, but it
    # cannot open a root that is not there yet. `mkdirs_within` creates a target's *parents*, so
    # the instance directory is asked for as the parent of the first file that goes into it —
    # through the same walk, rather than with the `Path.mkdir(parents=True)` this project does
    # not allow into a lane that puts files into a repository.
    fsops.mkdirs_within(root, f"{name}/{OVERLAY_FILES[0]}")
    apply(target, plan(target, preset_defaults(name), templates()))
    return target


def create(
    owner: str,
    name: str,
    *,
    source: str,
    root: Path,
    runner: Runner,
    wait: Callable[[float], None] = time.sleep,
) -> Created:
    """Create `root/<name>`, from the template repository or from the shipped tree."""
    _segment("owner", owner)
    _segment("name", name)
    if source not in SOURCES:
        raise Refusal(f"source {source!r} is not one of {', '.join(SOURCES)}")
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
    return _from_template(owner, name, root=root, runner=runner, wait=wait)


def _from_template(
    owner: str, name: str, *, root: Path, runner: Runner, wait: Callable[[float], None]
) -> Created:
    target = root / name
    if _populated(target):
        # §6.1 asks for idempotence in as many words: `gh` may give up on the clone with the
        # repository already created, so the second run finds a tree and must not re-create.
        return Created(target, "template", (f"{target} already exists and was left alone",))
    slug = f"{owner}/{name}"
    runner.run(
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

    # Nothing arrived. Which of the two failures it was decides whether waiting can help, so ask
    # before retrying: `gh repo view` printing the name back is the evidence the repository
    # exists and the clone raced its generation.
    view = runner.run(["gh", "repo", "view", slug, "--json", "name", "--jq", ".name"], root)
    raced = view.code == 0 and bool(view.stdout.strip())
    if raced:
        wait(RETRY_WAIT_SECONDS)
    # The clone is retried either way, and that is deliberate: `gh repo view` answering nothing
    # is not proof of absence — a rate limit, an expired token or a `gh` that is not installed
    # answers the same — and one fast failure is cheaper than refusing to try.
    runner.run(["git", "clone", "--", f"git@github.com:{slug}.git", name], root)
    if _populated(target):
        return Created(target, "template", (f"cloned {slug} on the second attempt",))
    raise Failure(
        f"{slug} produced no tree at {target}: `gh repo create --clone` left nothing, and the "
        + ("retried" if raced else "one further")
        + " `git clone` brought nothing down either. "
        + (
            "GitHub reports the repository exists, so generation may still be running — wait and "
            "clone it by hand"
            if raced
            else f"GitHub did not confirm the repository exists; check `gh auth status` and that "
            f"{owner}/{TEMPLATE_REPOSITORY} is reachable"
        )
    )


def _suffixed(value: object, suffix: str) -> str | None:
    """The renamed value, or `None` when it is already suffixed or not a name at all."""
    if not isinstance(value, str) or not value or value.endswith(f"-{suffix}"):
        return None
    return f"{value}-{suffix}"


def init_instance(root: Path, owner: str, *, runner: Runner) -> Initialised:
    """Make a generated overlay this owner's: name it after them, and install the secret scan.

    §6.1 wants the suffix "so two overlays never collide" — a harness installs a plugin by the
    name in its manifest, so two owners' overlays under one configuration directory would be one
    plugin fighting itself. Both manifests are rewritten through `fsops.write_within`: the
    overlay root *is* a root, so the contained walk applies and there is no carve-out to take.
    """
    suffix = _segment("owner", owner.strip().lower())
    renamed: list[str] = []
    notes: list[str] = []
    for relative in (PLUGIN_MANIFEST, MARKETPLACE_MANIFEST):
        if _rename(root, relative, suffix):
            renamed.append(relative)
    if renamed:
        notes.append(f"named this overlay after {suffix}: {', '.join(renamed)}")
    else:
        notes.append(f"both manifests already name {suffix}; nothing was renamed")
    notes.append(_install_hooks(root, runner))
    return Initialised(tuple(renamed), tuple(notes))


def _rename(root: Path, relative: str, suffix: str) -> bool:
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
        return False
    fsops.write_within(root, relative, json.dumps(document, indent=2) + "\n")
    return True


def _install_hooks(root: Path, runner: Runner) -> str:
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
