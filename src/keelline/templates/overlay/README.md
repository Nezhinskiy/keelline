# Your Keelline overlay

This repository is the private half of Keelline. It holds the things that are yours rather
than any one project's: the standing rules you want every session to start with, the notes
that span projects, and one record per repository binding that repository to this overlay.

**Keep it private.** Nothing here is meant to be published. It may name hosts, accounts and
the paths of environment files; it must never hold a credential, and two scans run to keep it
that way — a pre-commit hook and a workflow on every push.

**It is not Keelline.** The tool ships separately, as a public plugin and a command-line
program. This repository carries no code: it carries content Keelline reads, and it depends on
a Keelline recent enough to understand this layout. That dependency is *declared*, in
`.claude-plugin/plugin.json` under `keelline.requires` — and **nothing enforces it yet**. No
code in Keelline or in either harness reads that field, so an older Keelline pointed at this
overlay will not refuse; it will misread it. Until a release enforces it, the field is a record
of intent, and `keelline doctor` is what tells you which Keelline you are actually running.

## What is where

`keelline overlay create` renders fifteen files here. These are the ones that are
yours to fill in:

| Path | What it holds |
|---|---|
| `common/rules/` | your personal standing rules, injected at the start of every session |
| `common/memory/` | notes that belong to you rather than to one project |
| `common/claude/permissions.json` | **your own** `permissions.allow` rules. `keelline attach` merges this list into a bound repository's `.claude/settings.local.json`, and nothing else in the file is read — a `deny` list here reaches nothing. It ships empty, because a plugin author may never grant a permission; only you may, on your own instance. |
| `common/claude/hooks.json` | **your own** hook entries, merged into a bound repository the same way. Ships empty for the same reason. |
| `common/codex/` | the same two, for the other harness: `common.rules` is a standing-rule file `attach` copies into `.codex/rules/`. |
| `projects/<name>/` | one directory per bound repository: its record (`project.toml`), and its notes |
| `skills/` | the procedures a session follows against this overlay |

And these are the machinery. Leave them alone unless you know why:

| Path | What it holds |
|---|---|
| `hooks/hooks.json` | **this repository's own** hook entries as a plugin — not the same file as `common/claude/hooks.json`, which is what `attach` merges into *other* repositories. Both ship as `{"hooks": {}}`; this one fires here, that one fires there. |
| `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | what makes this repository installable as a Claude Code plugin, and the one-plugin marketplace that publishes it. `keelline overlay init` suffixes both names with your account. `version` is **this overlay's** own, not Keelline's, and starts at `0.0.0` because you have not released it; `keelline.requires` is the Keelline this layout needs, and is not enforced (above). |
| `.codex-plugin/plugin.json` | the same manifest for Codex. |
| `.pre-commit-config.yaml` | the gitleaks hook, pinned at a revision: the commit-time half of "no credential enters this repository". `keelline overlay init` installs it. |
| `.github/workflows/scan.yml` | the push-time half, with every action pinned to a commit sha. |
| `.gitignore` | env files, in every spelling, so a credential cannot be added by accident. |
| `README.md` | this file. |

Your `.env` files are denied to the agent by `keelline setup`, which writes those deny rules into
`~/.claude/settings.json` at machine scope — once, for every project on the machine. They are not
kept here, because a second copy of a security rule is a copy that drifts.

## Making it yours

Run `keelline overlay init` once after creating this repository. It suffixes the plugin and
marketplace names with your account so two overlays never collide, and installs the secret
scan. After that, `keelline attach` binds a repository to it and `keelline overlay upgrade`
refreshes the files you have not edited when a new Keelline is released.
