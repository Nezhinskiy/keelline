# Keelline

A methodology harness for coding agents: a bug ledger that lives in the repository, a
working memory whose index is rendered rather than written, guards that fail closed where
the platform lets them, and — designed, not yet shipped — an adoption state machine that
runs gates advisory until a repository has earned them. One plugin for Claude Code and
Codex, one Python package with **no runtime dependencies**.

> **Pre-1.0.** What ships: the memory store and its trust gate; the scaffolding engine that
> writes files into a repository; the guards over a shell call, a commit message and a test
> run; the bug ledger; the documentation and plan lints; `keelline setup`, which configures a
> machine from a preset; the private overlay — `overlay create`, `overlay init`,
> `overlay upgrade`, `overlay publish-template` — and `attach`/`detach`, which bind a
> repository to it and unbind it
> again; `keelline init`, which writes a repository's footprint from the shipped project
> templates, `keelline upgrade`, which refreshes it, and `keelline uninstall`, which takes it
> back; `keelline doctor`, which reports on the result; and `keelline assess`, which inventories
> what stands between a repository and enforcement. The hooks file that wires all
> of it into a session ships too, so installing the plugin is enough to make the guards fire
> and the memory bundles arrive. The first skills ship with them, and so do two command groups
> meant for a machine rather than for you — `hook`, which dispatches one harness event, and
> `release`, whose three commands (`check`, `notes`, `hashes`) are this repository's own
> discipline. **Not yet:** the adoption state machine, the memory MCP server, a
> hold-the-line baseline, the `uvx` form of the gate, and adapters for Cursor or Hermes — each
> leaves this list in the change that ships it. The [Quickstart](#quickstart) shows the three
> keys that are enough to start a project by hand, which `init` reads as your answers — a run
> that writes the file itself writes `[keelline] version`, `state` and `agents`, and `profile`
> when the repository carries a shipped profile's markers, beside `[project] name`,
> `base_branch` and `release_branch`, a `[ci]` table only when it has a released commit to pin
> or `--no-ci` asks for none, and no `[memory]` table at all.
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
  earned them. Designed; `keelline assess` reports what stands in the way, and the
  promotion command ships later.
- **A personal overlay that is itself a versioned plugin** with its own upgrade manifest,
  rather than a dotfiles sync. `keelline overlay create` renders one and `keelline attach`
  binds a repository to it. It also *declares* the Keelline it needs, in its plugin manifest;
  `keelline doctor` reads it and reports it when the Keelline running is too old — red when
  this project keeps its notes in that overlay, a warning when it does not — and a session in a
  bound repository says so once at its start.

Two more practices ride along and are named as such: every assertion ships with the
mutation that reddens it, and working memory is a routing table of hand-written lines, not
a summary. The principles behind all of it, with dated sources and an honest note where the
backing is thin, are in [docs/methodology/README.md](docs/methodology/README.md).

**This is not a replacement for superpowers.** `keelline setup --preset recommended` installs
it, and [context7](https://github.com/upstash/context7), on Claude Code — both ship in
Anthropic's own official marketplace, so `setup` needs no separate registration step for
either. **Codex has no verified non-interactive marketplace source for either plugin** (checked
against this project's own spike record and each plugin's own published install instructions,
2026-09-18): install `superpowers` and `context7` by hand there if you use Codex, the same way
you would install any other Codex plugin — `setup` reports this as a note rather than guessing a
marketplace name (nothing is vendored on a guess). The adoption skill will delegate to
superpowers where it is present. Designed; the adoption skill belongs to the package that ships
the state machine.

## Install

<!-- RELEASING.md section 2, step 5 replaces EVERYTHING between the two
`release-install` markers below — not just the first paragraph — with exactly the text in this
comment, at the first release, with X.Y.Z the version that was tagged. The extent is marked
rather than described because the replacement carries its own two code blocks: swapping only
the opening paragraph would leave the untagged install commands and the "From the first
release on" promise standing underneath it, so the released README would name two different
install commands and make a forward reference that the release itself had just falsified.
Written here so that the release commit is an edit and not a composition:

**Released as X.Y.Z.** Both commands below install that release. The plugin form takes the
tag, and `uv tool install keelline` resolves from PyPI:

As a Claude Code plugin:

```
/plugin marketplace add Nezhinskiy/keelline@vX.Y.Z
/plugin install keelline@keelline-marketplace
```

As a command-line tool:

```bash
uv tool install keelline
```
-->

<!-- release-install:begin -->

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

<!-- release-install:end -->

In CI, a project calls the reusable workflow at a commit SHA;
[docs/cli.md](docs/cli.md#the-reusable-workflow) shows the three lines.

**Requirements: Python 3.11 or newer, and a POSIX system.** Linux and macOS are supported and
tested; Windows is not. The containment this project is built on uses `openat` with
`O_NOFOLLOW` and `O_DIRECTORY`, which have no Windows equivalent.

## Quickstart

Three keys in a `keelline.toml` at the root of a repository start a project; every other key
takes the `recommended` preset's default, and [docs/cli.md](docs/cli.md#configuration) lists all
of them, annotated.

```toml
[keelline]
version = "0.1.0"

[project]
name = "widget"          # one lowercase path segment

[memory]
groups = ["developer"]   # the preset names four; the store below has one
```

`keelline init --yes` writes that file for you — the name from `origin`, the base branch, the
agent surfaces this repository carries — along with the documentation skeleton the other
commands expect and, once there is a Keelline release to pin, a CI workflow. Read it before it
runs; a `keelline.toml` you wrote yourself is read as your answers rather than replaced:

```bash
keelline init --yes --dry-run   # both plans, every file named, nothing written
keelline init --yes
```

The default memory mode keeps notes under `.keelline/local/memory/`, git-ignored, one
directory per group. Write one note and render the index:

```bash
mkdir -p .keelline/local/memory/developer
printf -- '---\nname: first-note\ndescription: "When to open this note"\n---\n\nThe note.\n' \
  > .keelline/local/memory/developer/first-note.md
keelline memory index      # renders .keelline/local/memory/MEMORY.md from the notes
keelline doctor            # sixteen checks over this installation, one line; --json has the remedies
```

`memory index` will tell you the notes reach no session until you say
`keelline memory trust --in-repo-memory` once — that is the trust gate, and
[The threat model, in one paragraph](#the-threat-model-in-one-paragraph) says why it exists.
Add `.keelline/local/` to `.gitignore` if it is not there already.

The other commands in [Commands](#commands) expect more of a repository than those three keys
create: `docs check` wants an `AGENTS.md`, `docs trail` a `docs/roadmap.md`, `bugs check` a
ledger entry. `keelline init --yes` writes all of those, which is what it is for; in a
repository you would rather grow by hand, add each path as you start using the command that
reads it — [docs/cli.md](docs/cli.md#configuration) lists every default.

## What it writes, and where

Keelline writes files. Being specific about which is the point of this section.

| Path | What it is | Written by |
|---|---|---|
| `keelline.toml` | Your project's configuration, committed | `keelline init`, once; you after |
| `docs/memory/` (configurable) | The note store, in `in-repo` and `overlay` mode | `keelline memory index` |
| `.keelline/local/memory/` | The note store in `local-only` mode, the default — git-ignored | `keelline memory index` |
| `<store>/MEMORY.md` | The rendered routing index. **Generated — do not hand-edit** | `keelline memory index` |
| `docs/bugs/` and `docs/bug-reports.md` (configurable) | One file per bug, and the generated index over them | `keelline init` writes the empty index and `docs/bugs/audits/README.md`; `keelline bugs new`, `bugs index` and `bugs renumber` after |
| `docs/roadmap.md` and `docs/roadmap-history.md` (configurable) | The forward track and the closed phases; in the roadmap, `docs trail` owns only the listing between its two markers | `keelline init` writes both files; `keelline docs trail` rewrites the listing |
| `docs/trail.toml` (beside the roadmap) | Which theme each design or plan document belongs to, and which are not plainly delivered. Read by `docs trail`, never written by it | `keelline init`, once; you after |
| `AGENTS.md`, `CLAUDE.md`, `docs/architecture/`, `docs/adr/`, `docs/runbooks/`, `docs/specs/`, `docs/plans/`, `.github/workflows/keelline.yml` | The project footprint: the documents every other command reads, plus the pinned CI caller. Written by `keelline init`, recorded in the manifest; `keelline upgrade` refreshes what you have not touched, and `keelline uninstall` takes it back | `keelline init` |
| `docs/keelline/rules/<profile>.md` (configurable) and `.claude/rules/keelline-<profile>.md` | The stack profile's rules, the one copy a project edits, and a path-scoped pointer at it for Claude Code (only when `[keelline] agents` lists `claude`) | `keelline init`, when `[keelline] profile` is set |
| `.keelline/assessment.json` | The inventory `keelline assess` last wrote, format 1 — git-ignored | `keelline assess`; `keelline uninstall` removes it |
| `.keelline/manifest.json` | The ledger of every scaffolded artifact | the scaffold engine |
| `.keelline/local/artifacts/` | The artifacts `[artifacts] local` keeps out of git, at the path each would have in the repository — git-ignored, never recorded in the manifest | `keelline init` and `keelline upgrade`, when `[artifacts] local` lists them; `keelline uninstall` takes them back |
| `.keelline/local/artifacts.json` | The record of the bytes Keelline last wrote under `.keelline/local/artifacts/`, so an unedited copy is refreshed or retired and an edited one is left. Git-ignored and never committed. Deleted, later runs judge a copy at its artifact's own place by what they render, and no longer find a copy left at an earlier place at all | the scaffold engine; `keelline uninstall` removes it |
| `~/.config/keelline/config.toml` | Machine-level settings: `[personal]`, `[overlay]`, `[machine]` | you, or `keelline setup` |
| `~/.config/keelline/trust.json` | Which repositories' committed notes you have approved | `keelline memory trust` |
| `hooks/hooks.json` and `hooks/run-hook.sh` | The zero-config wiring both harnesses read, and the wrapper they execute. **Shipped in the plugin; never written into a project** | nothing — they are part of the plugin |
| `${CLAUDE_PLUGIN_DATA}/keelline/` | Once-per-session markers and the hook diagnostics log. Deleted with the plugin | the hook dispatcher |
| `.gitignore`, the `keelline:ignore` region | The block that keeps `.keelline/local/` and `.keelline/assessment.json` out of git. Recorded in the manifest when `init` writes it, and `detach` then leaves it | `keelline init`, or `attach` on a repository `init` has not set up |
| `.keelline/local/attach.json` | What `attach` added to this repository, so `detach` can take exactly that back — git-ignored by the region `attach` itself writes | `keelline attach` |
| `<overlay>/projects/<name>/project.toml` | Which remote this overlay is bound to for this project, and when it was first attached | `keelline attach` |

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
# Initialising a project
keelline init --questions                             # each default, where it came from, the flag that changes it
keelline init --yes --dry-run                         # both reports, nothing written
keelline init --yes                                   # write the footprint and record every file
keelline upgrade --dry-run                            # what a newer Keelline would refresh
keelline upgrade                                      # refresh untouched files; move version and pin
keelline upgrade --force docs/roadmap.md              # overwrite one file you edited
keelline uninstall --dry-run                          # what would go; what you edited stays

# Memory
keelline memory index                                 # render MEMORY.md from the notes
keelline memory index --check                         # report drift, write nothing
keelline memory trust --in-repo-memory                # approve the notes inside this repository
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
keelline test attribute --command "uv sync --locked && uv run pytest tests/x.py::t"   # the change, or the environment: three runs, one verdict

# The private overlay
keelline overlay create --owner you --name keelline-private --local   # render one here, no network call at all
keelline overlay create --owner you --name keelline-private --template  # from <owner>/keelline-overlay-template, which you publish yourself
keelline overlay init --owner you --root ../keelline-private   # name it after you; install the secret scan
keelline overlay upgrade --root ../keelline-private --dry-run  # what a release would refresh
keelline overlay publish-template --owner you                  # what it would create, mark and push; nothing leaves yet
keelline overlay publish-template --owner you --yes            # publish the template repository from this checkout

# Binding a repository to the overlay
keelline attach --store ../keelline-private/projects/widget/memory --check   # the binding and the permission diff, writing nothing
keelline attach --store ../keelline-private/projects/widget/memory --yes     # merge the diff you just read, and link the notes in
keelline attach --store ../keelline-private/projects/widget/memory --trust-remote  # record this remote although the overlay recorded another
keelline detach                                       # remove what attach added; the binding record stays

# Machine setup
keelline setup --preset recommended                   # the machine configuration, deny rules and preset plugins
keelline setup --preset recommended --overlay ../keelline-private   # record an existing overlay; no --yes needed
keelline setup --preset recommended --overlay create:you/keelline-private --yes  # create one on GitHub; --yes is the consent
keelline setup --preset recommended --settings ~/dotfiles/claude/settings.json   # a linked settings file, written where it really is
keelline setup --git-hooks                             # install the commit-message hook into this repository
keelline setup --git-hooks --uninstall                 # remove it; restore the hook it chained to

# Assessing a repository
keelline assess                                       # every gate and probe; the whole inventory in .keelline/assessment.json

# Diagnosing an installation
keelline doctor                                       # sixteen checks over this installation, one line
keelline doctor --json                                # every check with its status, detail and remedy

# Internal and release
keelline hook SessionStart                            # dispatch one harness hook event (internal)
keelline release check                                # one version everywhere (this repository's own)
keelline release check --tag v1.2.3                   # and the tag agrees, with nothing left in changelog.d
keelline release notes --version 1.2.3 --draft        # render the section towncrier would write
keelline release notes --version 1.2.3                # assemble CHANGELOG.md from changelog.d
keelline release hashes --check                       # the shipped files still match the release record
```

Every `memory`, `bugs`, `docs` and `plan` command, and `assess`, takes `--root` (default: the current
directory) and `--machine` (read a machine configuration file other than the default);
`memory` commands and `docs check` take `--store` as well. `keelline overlay` is the
exception: its `--root` names the directory an overlay is created in or the overlay itself,
not a project root, and it reads no `keelline.toml`. `--json` is accepted anywhere and
prints one machine-readable object instead of one line. The commands that report a list of
findings — `bugs check`, `docs check`, `memory refs`, `plan check`, `test audit-entrypoints` —
all spell it `findings`, whatever their summary line calls them; every other command's keys
are its own and are listed with it in [docs/cli.md](docs/cli.md).

Exit codes are the same everywhere: **0** success, **1** findings, **2** a refusal or an
internal error. A caller must never read 2 as permission. Two commands are deliberately
outside that rule. `keelline test audit-entrypoints` exits **0** even when it has findings,
and lists them under `--json`, because its candidates are for triage and gating on them
is not shipped yet. And `keelline hook` refuses with **2** on an internal
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

`memory.mode` decides where the store is. `local-only` (the default — `.keelline/local/memory`,
git-ignored) and `in-repo` (committed) both put the notes **inside the repository**, so both are
behind the trust gate; `overlay` (a directory of links into a machine-level overlay shared across
your projects) puts them outside it, and notes that are yours need no approval. The gate keys on
where a note actually sits, never on what the repository's own `keelline.toml` declares — a clone
that wrote `mode = "local-only"` would otherwise gate itself.

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

`skills/` ships two ported skills (`close-bug`, `memory-sweep`), six authored ones
(`file-bug`, `sweep-defect-class`, `review-plan-three-lenses`, `attribute-failure`,
`run-correctness-audit`, `retro-to-guard`), and thin wrappers for the commands the CLI
registers; `agents/` ships a read-only `code-navigator`. Every skill is written in action
language — never a harness tool's name — with the per-harness mapping in
[skills/README.md](skills/README.md), and every `keelline …` invocation in a skill is
parsed against the real parser by a test. A wrapper written ahead of its command is listed in
that test until the command ships; none is today.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — it states the three rules a change here has to satisfy,
which are not obvious from the code. Security reports go through
[SECURITY.md](SECURITY.md), never a public issue.

## License

MIT. See [LICENSE](LICENSE).
