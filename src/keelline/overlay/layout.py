"""What the overlay is called, directory by directory — names and nothing else.

A leaf module on purpose. `attach` needs to know where a project's record and a project's
notes sit inside the overlay, and it must be able to ask without importing a command module or
the scaffold engine; keeping the names here is what makes that possible.

`PROJECTS` and `PROJECT_RECORD` are **not** redefined here: they come from `keelline.memory.api`,
because `memory.store` already resolves this layout for the hook path and two spellings of one
layout is one more place for them to stop agreeing. `memory.store.COMMON` stays where it is for
the same reason in reverse — it is `Path("common") / "memory"`, that module's *path into* the
overlay rather than this module's *name for* a directory, and defining either in terms of the
other is how they would drift.
"""

from __future__ import annotations

from keelline.memory.api import PROJECTS

COMMON = "common"
COMMON_RULES = f"{COMMON}/rules"
COMMON_MEMORY = f"{COMMON}/memory"
COMMON_CLAUDE = f"{COMMON}/claude"
COMMON_CODEX = f"{COMMON}/codex"
PLUGIN_MANIFEST = ".claude-plugin/plugin.json"
MARKETPLACE_MANIFEST = ".claude-plugin/marketplace.json"
# The Codex half of `PLUGIN_MANIFEST`, named here rather than spelled as a literal inside
# `OVERLAY_FILES`: `overlay init` has to suffix it for the same reason it suffixes the other
# two — a harness installs a plugin by the name in its manifest, and this project ships a Codex
# half of everything else.
CODEX_PLUGIN_MANIFEST = ".codex-plugin/plugin.json"

# Every file `templates/overlay/` ships, in the order the plan's table lists them. The list and
# the tree are two statements of one thing: `tests/overlay/test_template.py` asserts each way
# round, so a file deleted from the tree and a file added to it without a line here are both
# caught rather than one of them.
# The two files an overlay carries that can grant a capability, and the reason `overlay upgrade`
# has a decision list at all: §6.1 diffs these and asks about them "regardless of hash", because
# a hash match is not consent for a permission or a hook entry. Named once, unpacked into
# OVERLAY_FILES below, and published as CAPABILITY_FILES: one spelling, so a rename here is a
# rename everywhere. The list used to be derived by filtering OVERLAY_FILES against a second
# spelling of the two names, under a comment claiming they were not spelled twice.
CAPABILITY_NAMES = (f"{COMMON_CLAUDE}/permissions.json", f"{COMMON_CLAUDE}/hooks.json")

# A directory's own documentation rather than a file in its own right: `overlay create`
# drops one of these into each directory the owner fills, and the template README describes
# those as directories on purpose. `tests/overlay/test_template.py` accounts for the tree
# by this rule; a fourth such directory needs no edit there. The root `README.md` is not a
# placeholder — the rule applies to a basename BELOW a directory, never to the root.
PLACEHOLDER_NAMES = ("README.md", "SKILL.md")

OVERLAY_FILES = (
    PLUGIN_MANIFEST,
    MARKETPLACE_MANIFEST,
    CODEX_PLUGIN_MANIFEST,
    "hooks/hooks.json",
    "skills/attach/SKILL.md",
    f"{COMMON_RULES}/README.md",
    f"{COMMON_MEMORY}/README.md",
    *CAPABILITY_NAMES,
    f"{COMMON_CODEX}/common.rules",
    f"{PROJECTS}/README.md",
    ".pre-commit-config.yaml",
    ".github/workflows/scan.yml",
    ".gitignore",
    "README.md",
)

CAPABILITY_FILES = CAPABILITY_NAMES
