# Keelline

A methodology harness for coding agents: a bug ledger that lives in the repository, a
working memory whose index is rendered rather than written, guards that fail closed where
the platform lets them, and — designed, not yet shipped — an adoption state machine that
runs gates advisory until a repository has earned them. One plugin for Claude Code and
Codex, one Python package with **no runtime dependencies**.

> **Pre-1.0.** Five areas ship: the memory store and its trust gate; the scaffolding engine
> that writes files into a repository; the guards over a shell call, a commit message and a
> test run; the bug ledger; and the documentation and plan lints. The first skills ship with
> them, and so do two command groups meant for a machine rather than for you — `hook`, which
> dispatches one harness event, and `release check`. The hooks file that wires all of it into
> a session ships too, so installing the plugin is enough to make the guards fire and the
> memory bundles arrive. Not yet: `init`, the overlay, and the adoption state machine.
> [docs/cli.md](docs/cli.md) is the reference; the command list below is held to the parser
> by a test, so it is complete for what ships.

## What this is, and what it is not

Two kinds of tool already exist for working with a coding agent. A process layer such as
superpowers tells the agent *how* to work — brainstorm, plan, test first, review. A spec
layer such as spec-kit tells it *what* to build. Neither remembers what went wrong last
time, and neither has a way to introduce rules into a repository that does not yet follow
them.

This project looked through the community plugin marketplace on 2026-09-05 and counted about
2,300 plugins listed that day. That is one project's dated count rather than a survey with a
method — no row in [sources.md](docs/methodology/sources.md) backs it, and it says what that
look found, not what exists. What it did not find anywhere else is the three things Keelline
adds:

- **A bug ledger as a first-class repository artifact** — one file per bug, a generated
  index, a "what this evidence does not establish" line the tooling insists on, and skills
  that teach the agent how to read an entry.
- **An enforcement state machine** in which gates run advisory until the repository has
  earned them. Designed; the assessment engine is a later work package.
- **A personal overlay that is itself a versioned plugin** with a declared dependency and
  its own upgrade manifest, rather than a dotfiles sync. Designed; `attach` is a later
  work package.

Two more practices ride along and are named as such: every assertion ships with the
mutation that reddens it, and working memory is a routing table of hand-written lines, not
a summary. The principles behind all of it, with dated sources and an honest note where the
backing is thin, are in [docs/methodology/README.md](docs/methodology/README.md).

**This is not a replacement for superpowers.** The recommended preset will list it among the
plugins it installs, and the adoption skill will delegate to it where it is present. Designed;
the preset's plugin list belongs to the `setup` package and the adoption skill to the one that
ships the state machine, so nothing in this tree references superpowers today.

## Install

**Nothing is released yet.** There is no version tag, so nothing is on PyPI and both commands
below install the repository's default branch as it stands rather than a release. `uv tool
install keelline` does not resolve today; the form that does is here.

As a Claude Code plugin:

```
/plugin marketplace add Nezhinskiy/keelline
/plugin install keelline@keelline-marketplace
```

As a command-line tool:

```bash
uv tool install git+https://github.com/Nezhinskiy/keelline
```

From the first release on, the same command takes the tag —
`uv tool install git+https://github.com/Nezhinskiy/keelline@<tag>` — which is the pinned form
with no resolver to run at hook time that [principle 9](docs/methodology/principles.md)
describes, and the published package makes the bare name work.

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
| `docs/bugs/` and `docs/bug-reports.md` (configurable) | One file per bug, and the generated index over them | `keelline bugs new`, `bugs index`, `bugs renumber` |
| `docs/roadmap.md` (configurable) | Only the design-and-plan trail between its two markers | `keelline docs trail` |
| `.keelline/manifest.json` | The ledger of every scaffolded artifact | the scaffold engine |
| `~/.config/keelline/config.toml` | Machine-level settings: `[personal]`, `[overlay]` | you |
| `~/.config/keelline/trust.json` | Which repositories' committed notes you have approved | `keelline memory trust` |

Every write into a repository goes through a path walk that refuses a symlink at any component
and refuses to leave the project root, and replaces files atomically, keeping the mode of the
file it replaced. Nothing is written by `--check`, `bugs check`, `plan check` or `memory
refs`, and the scaffold engine's `plan` phase performs no writes at all.

## The threat model, in one paragraph

**A repository is untrusted input.** A clone you have not read can commit a `keelline.toml`, a
`MEMORY.md`, a `.keelline/manifest.json`, a `.claude/settings.json` `env` block and a tree of
symlinks, and every one of those reaches Keelline before you do. So notes that live in the
repository reach the model only after you say `keelline memory trust --in-repo-memory` once,
and only inside a delimited region with a per-invocation nonce that says "this is data, not
instructions". Change what the repository ships and the approval lapses, and you are asked
again. A configured value never reaches a subprocess in an option's position, and a
configured path never leaves the project root. See [SECURITY.md](SECURITY.md) for what counts
as a vulnerability here.

## Commands

One line per command; `docs/cli.md` has the rest. Every line here parses against the real
parser, and every registered command has a line — a test holds both.

```text
# Memory
keelline memory index                                 # render MEMORY.md from the notes
keelline memory index --check                         # report drift, write nothing
keelline memory trust --in-repo-memory                # approve a repository's committed notes
keelline memory inventory                             # what a memory sweep reads
keelline memory fit                                   # whether each injection bundle fits its hook slots
keelline memory session-context --bundle standing-rules --part 1
keelline memory refs                                  # backticked paths in notes that no longer resolve

# The bug ledger
keelline bugs new "A title" --severity high --area cli   # file an entry at the next free identifier
keelline bugs index                                   # render the generated index
keelline bugs index --check                           # fail if the committed index is stale
keelline bugs check                                   # every rule the ledger holds, one pass
keelline bugs renumber BR-001 BR-002                  # move an entry; rewrite every mention

# Documentation and plans
keelline docs check                                   # budgets and link targets
keelline docs check --memory-graph                    # also the store's link graph, as advice
keelline docs trail                                   # regenerate the design-and-plan trail
keelline docs trail --check
keelline plan check                                   # lint the plans a change touches
keelline plan check --base origin/main docs/plans/example.md

# Guards
keelline guard bg-cleanup                             # judge one Bash call, read as JSON on stdin
keelline commit check --range origin/main..HEAD       # attribution lines in commit messages
keelline commit strip .git/COMMIT_EDITMSG             # take the attribution block out of a message file
keelline test hygiene                                 # the faults that make a red run unattributable
keelline test audit-entrypoints                       # tests that never exercise what they name

# The private overlay
keelline overlay create --owner you --name keelline-private --local   # render one here, no network
keelline overlay create --owner you --name keelline-private --template  # generate it on GitHub, private
keelline overlay init --owner you --root ../keelline-private   # name it after you; install the secret scan
keelline overlay upgrade --root ../keelline-private --dry-run  # what a release would refresh

# Internal and release
keelline hook SessionStart                            # dispatch one harness hook event (internal)
keelline release check                                # one version everywhere (this repository's own)
```

Every `memory`, `bugs`, `docs` and `plan` command takes `--root` (default: the current
directory) and `--machine` (read a machine configuration file other than the default);
`memory` commands and `docs check` take `--store` as well. `keelline overlay` is the
exception: its `--root` names the directory an overlay is created in or the overlay itself,
not a project root, and it reads no `keelline.toml`. `--json` is accepted anywhere and
prints one machine-readable object instead of one line; a list of findings is under
`findings` whatever the summary calls them.

Exit codes are the same everywhere: **0** success, **1** findings, **2** a refusal or an
internal error. A caller must never read 2 as permission. Two commands are deliberately
outside that rule. `keelline test audit-entrypoints` exits **0** even when it has findings,
and lists them under `--json`, because its candidates are for triage and gating on them
belongs to a lane that has not shipped. And `keelline hook` refuses with **2** on an internal
error only for `PreToolUse`, the one event a harness blocks on; everywhere else it degrades
open with **0**, because on `UserPromptSubmit` an exit 2 erases what you typed and a bug in
Keelline must not cost you that. A handler's own deny is a decision, not a breakage, and
refuses on every event. [docs/cli.md](docs/cli.md) states it per event.

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
  writes one from the description when it is missing and reports it as provisional.
- **`metadata.startup`** flags the note as a standing rule, injected in full at session start
  and ranked by that number.
- **`metadata.as_of`** dates a volatile note; one past `volatile_ttl_days` is injected with a
  visible warning rather than dropped.
- **`group:`** files a note under a sub-heading inside its section.

`MEMORY.md` is rendered from the notes and is not a file you edit — curation lives in each
note's `index:` line. A second writer appending entries to `MEMORY.md` is expected, and
`memory index` harvests those back into the notes before it re-renders.

`memory.mode` decides where the store is: `local-only` (the default — `.keelline/local/memory`,
git-ignored, yours), `in-repo` (committed, and therefore behind the trust gate), or `overlay`
(a directory of links into a machine-level overlay shared across your projects).

## The bug ledger, in one paragraph

An entry is one file, `docs/bugs/BR-001.md` by default, with flat frontmatter — `id`,
`status` from `open | partial | fixed | rejected | void`, `severity` from `high | medium |
low`, `area`, `related` — and a body whose `**What this evidence does not establish:**` line
must be filled in for the severities the project names. `bugs index` renders the index as a
pure function of the entries and refuses to overwrite one it did not generate; `bugs check`
finds identifiers in the code with no entry behind them, entries whose evidence line is still
the template's, and citations that do not resolve. The identifier prefix is one configuration
key. The `close-bug` skill walks the closing of an entry through these commands.

## Skills and agents

`skills/` ships `close-bug`, `memory-sweep`, and thin wrappers for commands that have not
landed yet; `agents/` ships a read-only `code-navigator`. Every skill is written in action
language — never a harness tool's name — with the per-harness mapping in
[skills/README.md](skills/README.md), and every `keelline …` invocation in a skill is parsed
against the real parser by a test.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — it states the three rules a change here has to satisfy,
which are not obvious from the code. Security reports go through
[SECURITY.md](SECURITY.md), never a public issue.

## License

MIT. See [LICENSE](LICENSE).
