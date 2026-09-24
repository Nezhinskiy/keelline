"""Every harness Keelline serves, as values in one registry.

A harness is served first by the `AGENTS.md` region, which `project.templates` renders and
every harness that reads the standard sees. Where a harness reads something better natively,
its `render_profile` renders a profile into that form. `settings` names the committed files in
which it reads hook entries, which `assess` inventories; `marker_dir` is the directory whose
presence says a repository uses it. A harness is a value, not a class: adding one is one more
value in `HARNESSES`, and nothing that reads the registry changes.

Code that needs a harness fact asks this registry. Three modules older than it still spell
their own settings files: `doctor`, `setup` and `attach`. `doctor` walks one no field here
models, the uncommitted `.claude/settings.local.json`, so moving it onto the registry is its
own change.

A name `[keelline] agents` lists and no harness answers to is counted, never refused and never
printed: the list is repository-authored, and a project may name a harness a later Keelline
serves.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from keelline.profiles import Profile


@dataclass(frozen=True)
class Rendition:
    """One file a harness reads natively, rendered from a profile."""

    artifact_id: str
    target: str
    render: Callable[[], str]


@dataclass(frozen=True)
class Harness:
    name: str
    marker_dir: str
    settings: tuple[str, ...]
    # The profile, and the repository-relative path of its rules file.
    render_profile: Callable[[Profile, str], Rendition] | None = None


CLAUDE_DIR = ".claude"
POINTER = (
    "This repository's `{name}` rules are in `{rules}`; open that file before editing a file "
    "these paths match. It is the one copy, and changes to the rules go there.\n"
)


def _claude_rule(profile: Profile, rules: str) -> Rendition:
    """A path-scoped rule whose body points at the one copy of the rules, and copies nothing.

    `paths:` is the one frontmatter field Claude Code reads in a rules file, and a rule under it
    loads when the session reads a matching file, not on every prompt. The body is one sentence
    rather than the rules themselves: a copy would drift from the file the project edits, and
    an import inside a rules file is not documented behaviour. `keelline-` in the file name says
    who owns it and leaves `<profile>.md` free for the project's own rule.
    """
    # `json.dumps` quotes each glob as a YAML double-quoted scalar. The globs are the profile's
    # own and carry `*`, which bare YAML would read as an alias.
    head = "---\npaths:\n" + "".join(f"  - {json.dumps(g)}\n" for g in profile.scope) + "---\n\n"
    body = POINTER.format(name=profile.name, rules=rules)
    return Rendition(
        "claude-rules", f"{CLAUDE_DIR}/rules/keelline-{profile.name}.md", lambda: head + body
    )


CLAUDE = Harness("claude", CLAUDE_DIR, (f"{CLAUDE_DIR}/settings.json",), _claude_rule)
# Codex reads `AGENTS.md` from the root down and no other instruction file, and follows no
# import; `.codex/rules` holds command-execution policy, not instructions. The region is how a
# profile reaches it, and there is nothing further to render.
CODEX = Harness("codex", ".codex", (".codex/hooks.json",))
HARNESSES: tuple[Harness, ...] = (CLAUDE, CODEX)


def select(agents: Sequence[str]) -> tuple[tuple[Harness, ...], int]:
    """The harnesses `agents` names, in registry order, and how many names none answers to."""
    listed = set(agents)
    chosen = tuple(harness for harness in HARNESSES if harness.name in listed)
    unknown = len(listed - {harness.name for harness in HARNESSES})
    return chosen, unknown
