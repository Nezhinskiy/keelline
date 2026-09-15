# Keelline

A methodology harness for coding agents — a bug ledger, curated working memory, guards, and an
adoption state machine — packaged as one plugin for Claude Code and Codex, and as a Python
package with **no runtime dependencies**.

> **Pre-1.0, and early.** Two areas ship today: the memory store and its trust gate, and the
> scaffolding engine that writes files into a repository. The ledger, the guards and the
> adoption state machine are not here yet. The CLI surface below is what exists.

## Install

As a Claude Code plugin:

```
/plugin marketplace add Nezhinskiy/keelline
/plugin install keelline@keelline-marketplace
```

As a command-line tool:

```bash
uv tool install keelline
```

**Requirements: Python 3.11 or newer, and a POSIX system.** Linux and macOS are supported and
tested; Windows is not. The containment this project is built on uses `openat` with
`O_NOFOLLOW` and `O_DIRECTORY`, which have no Windows equivalent.

## What it writes, and where

Keelline writes files. Being specific about which is the point of this section.

| Path | What it is | Written by |
|---|---|---|
| `keelline.toml` | Your project's configuration, committed | you, or a later `init` lane |
| `docs/memory/` (configurable) | The note store, in `in-repo` and `overlay` mode | `keelline memory index` |
| `.keelline/local/memory/` | The note store in `local-only` mode, the default — git-ignored | `keelline memory index` |
| `<store>/MEMORY.md` | The rendered routing index. **Generated — do not hand-edit** | `keelline memory index` |
| `.keelline/manifest.json` | The ledger of every scaffolded artifact | the scaffold engine |
| `~/.config/keelline/config.toml` | Machine-level settings: `[personal]`, `[overlay]` | you |
| `~/.config/keelline/trust.json` | Which repositories' committed notes you have approved | `keelline memory trust` |

Every write into a repository goes through a path walk that refuses a symlink at any component
and refuses to leave the project root, and replaces files atomically, keeping the mode of the
file it replaced. Nothing is written by `--check`, and the scaffold engine's `plan` phase
performs no writes at all.

## The threat model, in one paragraph

**A repository is untrusted input.** A clone you have not read can commit a `keelline.toml`, a
`MEMORY.md`, a `.keelline/manifest.json`, a `.claude/settings.json` `env` block and a tree of
symlinks, and every one of those reaches Keelline before you do. So notes that live in the
repository reach the model only after you say `keelline memory trust --in-repo-memory` once,
and only inside a delimited region with a per-invocation nonce that says "this is data, not
instructions". Change what the repository ships and the approval lapses, and you are asked
again. See [SECURITY.md](SECURITY.md) for what counts as a vulnerability here.

## Commands

```
keelline memory index              # render MEMORY.md from the notes; --check reports drift
keelline memory trust --in-repo-memory
keelline memory inventory          # what a memory sweep reads
keelline memory fit                # whether each injection bundle fits its hook slots
keelline memory session-context --bundle <name> [--part N]
keelline release check             # one version across six sources (this repository's own)
keelline hook <event>              # internal: dispatch one harness hook event
```

Every `memory` command takes `--root` (default: the current directory), `--store` (resolve the
store at a path), and `--machine` (read a machine configuration file other than the default).
`--json` is accepted anywhere and prints a machine-readable object instead of one line.

Exit codes are the same everywhere: **0** success, **1** findings, **2** a refusal or an
internal error. A caller must never read 2 as permission.

### `keelline memory trust`

The one command with a consequence worth stating twice. It records a hash of everything the
store yields — every note, `MEMORY.md`, and the repository-controlled configuration that is
rendered into it — against the store's absolute path, in `~/.config/keelline/trust.json`.

You are saying: *I have read what this repository committed under its memory directory, and it
may reach the model as data.* Any later change to any of those files makes the hash disagree
and the approval lapse until you look again and re-run it. A store whose notes are yours —
`overlay` mode, where the notes live in your own machine-level overlay — needs no approval, and
recording one for it is inert.

## Memory, in one page

A note is a Markdown file with frontmatter, under a group directory in the store:

```markdown
---
name: prefer-uv
description: This project uses uv, never pip
index: adding a dependency → use uv add
metadata:
  type: project
  startup: 1
---

Run `uv add`, not `pip install`. The lockfile is committed and CI runs `uv sync --locked`.
```

- **`index:`** is the routing line — the trigger and the answer, not a summary. `memory index`
  writes one from the description when it is missing.
- **`metadata.startup`** flags the note as a standing rule, injected in full at session start
  and ranked by that number.
- **`metadata.as_of`** dates a volatile note; one past `volatile_ttl_days` is injected with a
  visible warning rather than dropped.

`MEMORY.md` is rendered from the notes and is not a file you edit — curation lives in each
note's `index:` line. A second writer appending entries to `MEMORY.md` is expected, and
`memory index` harvests those back into the notes before it re-renders.

`memory.mode` decides where the store is: `local-only` (the default — `.keelline/local/memory`,
git-ignored, yours), `in-repo` (committed, and therefore behind the trust gate), or `overlay`
(a directory of links into a machine-level overlay shared across your projects).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — it states the three rules a change here has to satisfy,
which are not obvious from the code. Security reports go through
[SECURITY.md](SECURITY.md), never a public issue.

## License

MIT. See [LICENSE](LICENSE).
