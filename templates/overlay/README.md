# Your Keelline overlay

This repository is the private half of Keelline. It holds the things that are yours rather
than any one project's: the standing rules you want every session to start with, the notes
that span projects, and one record per repository binding that repository to this overlay.

**Keep it private.** Nothing here is meant to be published. It may name hosts, accounts and
the paths of environment files; it must never hold a credential, and two scans run to keep it
that way — a pre-commit hook and a workflow on every push.

**It is not Keelline.** The tool ships separately, as a public plugin and a command-line
program. This repository carries no code: it carries content Keelline reads, and it depends on
a Keelline recent enough to understand this layout.

## What is where

| Path | What it holds |
|---|---|
| `common/rules/` | your personal standing rules, injected at the start of every session |
| `common/memory/` | notes that belong to you rather than to one project |
| `common/claude/` | permissions and hook entries merged into a bound repository |
| `common/codex/` | the same, for the other harness |
| `projects/<name>/` | one directory per bound repository: its record, and its notes |
| `skills/` | the procedures a session follows against this overlay |

## Making it yours

Run `keelline overlay init` once after creating this repository. It suffixes the plugin and
marketplace names with your account so two overlays never collide, and installs the secret
scan. After that, `keelline attach` binds a repository to it and `keelline overlay upgrade`
refreshes the files you have not edited when a new Keelline is released.
