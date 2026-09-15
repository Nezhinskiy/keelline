# Command reference

Every command, what it reads, what it writes, and what each exit code means. `keelline --help`
gives you the one-line version; this is the rest.

Three things hold everywhere:

- **`--json` is accepted anywhere** and prints one machine-readable object instead of one line.
  It is not declared per command — the frame strips it from `argv` before parsing.
- **Exit codes**: `0` success, `1` findings, `2` a refusal or an internal error. A caller that
  treats `1` as "proceed anyway" must still never treat `2` that way — a refusal is a boundary,
  not a low-confidence result.
- **Every `memory` command takes the same three options**, described once here rather than five
  times below.

| Option | Meaning |
|---|---|
| `--root PATH` | The project root. Default: the current directory. |
| `--store PATH` | Resolve the note store at this path instead of where the configuration says. An override of *where the notes are*, not of the rules about them: the same containment and overlay-binding checks apply, so it is not a way around the trust gate. |
| `--machine PATH` | Read this machine configuration file instead of `~/.config/keelline/config.toml`. Mostly for tests and for running against a second machine profile; it also decides which `trust.json` is consulted. |

---

## `keelline memory index`

Rewrite every note's `index:` line and re-render `MEMORY.md` from them.

```bash
keelline memory index            # write
keelline memory index --check    # report drift, write nothing
```

**Reads** every `*.md` under each configured group, and the current `MEMORY.md`.
**Writes** each note whose `index:` line it filled in, and `MEMORY.md` — in overlay mode, the
file the symlink points at, not the link.

What it does, in order:

1. **Harvests.** A second writer — you, another session — may have appended
   `- [trigger → answer](group/note.md)` lines to `MEMORY.md`. Those are read back into each
   note's `index:` frontmatter first, so nothing a session wrote is lost by regenerating.
2. **Invents what is missing.** A note with no `index:` gets a provisional one from its
   `description`. Provisional lines are reported so you can curate them.
3. **Renders.** One section per configured group, a note's `group:` value as a sub-heading
   inside it, ordered by `startup` rank first, then by `group_order`, then by name — so a
   note ranked for the session leads its section whatever its position within a sub-heading.

`--check` exits `1` when the index has drifted, when it is over its word budget, when it is past
the harness's line or byte caps, or when a file in the store cannot be parsed as a note. The
same findings are printed on the write path too — they just do not fail it, because `--check`
is the mode that fails a build.

Exits `2` if `MEMORY.md` is a symlink this store may not follow (see §9.1's target rule: outside
overlay mode a symlinked index is refused outright; in overlay mode only a link into *this*
project's own share of the recorded overlay is honoured).

**Trust interacts with this command**, and the interaction is the non-obvious part: `memory
index` rewrites the very files the trust hash covers, so it would revoke the approval it depends
on. It does not — it re-records the hash across exactly the files it itself wrote, carrying every
other file's approved digest forward unchanged. If something else changed the store while the
command ran, it refuses to carry trust and says so.

## `keelline memory trust --in-repo-memory`

Record that the notes this repository committed may reach the model.

The flag is required and never read: it is a confirmation gesture, not a switch, and it is what
stops this from being a bare, trivially scripted command.

**Reads** every file the store yields. **Writes** `~/.config/keelline/trust.json` (or the file
beside `--machine`).

The hash covers every note, `MEMORY.md`, and the repository-controlled configuration rendered
into it, keyed by the store's absolute path. Change any of it and the approval lapses — you are
asked again rather than silently kept. Notes that are *yours* (an overlay store) need no
approval; recording one is inert rather than dangerous.

Exits `2` if `trust.json` exists and does not parse. It holds every project's approval on the
machine, so nothing will overwrite a file it could not read — repair or delete it.

## `keelline memory session-context --bundle <name> [--part N]`

Render one injection bundle. This is what a `SessionStart` hook entry invokes; you will rarely
run it by hand except to see what a session actually receives.

| Bundle | What it is |
|---|---|
| `preset-rules` | Rules from your own preset. Never repository content, so never gated. |
| `standing-rules` | Every note flagged `startup`, in full, ranked. Never truncated — only flagged when the set outgrows its budget, because a standing rule that does not arrive is a standing rule that gets broken. |
| `volatile-notes` | Dated, perishable notes, in full; over budget, descriptions only. |
| `index` | `MEMORY.md` itself, so the model can route. |

Each bundle is emitted across numbered parts, because the harness caps each hook entry's output
independently. `--part N` selects one; a part past the end prints nothing and exits `0`. A part
that is a single block too large for one slot is withheld — the command prints a short notice
saying so instead, because the harness would otherwise truncate it and a truncated region loses
the marker that says where repository content ends. `keelline memory fit` names the block.

Output is deliberately **raw**, not JSON: the margin that keeps a bundle inside the platform cap
is additive only because there is no envelope and no escaping. Do not pass `--json` from a hook
entry.

When the store is repository data with no trust record, every bundle but `preset-rules` is
empty, and this command says nothing rather than explaining why — its output *is* what reaches
the model. `keelline memory index` and `keelline memory fit` are where the explanation is
printed, because those are the commands a person runs.

## `keelline memory inventory`

What a memory sweep reads: every note with its word count, type, `startup` rank, date, whether
it is stale, and whether its index line is curated, harvested or provisional. Plus totals.

Writes nothing.

## `keelline memory fit`

Whether each bundle fits the numbered hook entries declared for it. Exits `1` when one does not
— either it needs more parts than there are slots, or a single block is larger than one part
and would be truncated by the platform.

A bundle that fits because it is *empty* is not a bundle that fits, so the output also reports
whether the trust gate is open.

Writes nothing.

## `keelline release check`

Cross-checks the version across `pyproject.toml`, `uv.lock`, `src/keelline/__init__.py`, both
plugin manifests and `CHANGELOG.md`. Exits `1` naming every source that disagrees.

This is discipline for **the Keelline repository itself**, not something Keelline offers your
project. See [RELEASING.md](../RELEASING.md).

## `keelline hook <event>`

Internal. Reads a hook payload on stdin, dispatches it to every handler registered for that
event, and writes the harness's expected output.

Not something to run by hand. Its exit-code policy differs from every other command: an internal
error refuses (`2`) only on `PreToolUse`, and degrades open (`0`) everywhere else — on
`UserPromptSubmit` an exit `2` erases what you typed, so a bug in Keelline must not cost you
your prompt.

## `keelline guard bg-cleanup`

Judge one Bash call for a background leak. Reads one JSON object on stdin — a whole hook
payload, or a bare `tool_input` with `command` and `run_in_background` — and answers `2` when
the call would be refused (a `&`-backgrounded job with no `trap … EXIT`, or a backgrounded
command that begins with `sleep`), `1` when it carries a trailing restore no trap protects, and
`0` otherwise. Anything it cannot read is `2`: this is the fail-closed row of the CLI table,
and a guard that guessed would be guessing.

This is the same judgement the `PreToolUse` `Bash` hook makes; the command exists so a CI
smoke test and a person can ask it without a harness. **Writes** nothing.

## `keelline commit check --range RANGE`

Every message in `RANGE` (a `git log` revision range, e.g. `main..HEAD`), for lines in its
final paragraph that are an AI/tool attribution trailer or footer: a `-by:` trailer whose
address is at a vendor's domain or whose name is a product, a `Generated with <tool>` footer,
or a line that is only `AI-generated`. Body prose is never judged, and a person whose name
happens to be a vendor word is not a violation. `[commit_messages] attribution_check = false`
switches it off. Exits `1` naming each offence as `sha line N [label]` — never the text,
which is the repository's — and `2` when git cannot read the range or the range looks like an
option. **Writes** nothing. This is what the reusable workflow runs.

## `keelline commit strip FILE`

Rewrite a commit-message file in place with the attribution lines of its final paragraph
removed — never a line of the body. Exits `0` whether or not anything was stripped, and says
which; a message that is *only* attribution is left alone, because
emptying it aborts the commit with a confusing error and CI explains better. Refuses a symlink.
This is what the `prepare-commit-msg` hook that `keelline setup --git-hooks` installs calls;
`git commit --no-verify` skips `commit-msg` but not this hook. **Writes** `FILE`.

## `keelline test hygiene`

The two environment faults that make a red test run unattributable: uncommitted changes in
the tree, and `.pyc` files whose recorded source mtime no longer matches their source. Counts
both under `[ledger] code_roots` and exits `1` when either is present, `2` when git cannot
report the tree. The `PostToolUse` `Bash` hook delivers the same note once per context after a
red pytest run. **Writes** nothing.

## `keelline test audit-entrypoints`

Tests that never exercise what they name, in two shapes: an assertion whose value is produced
by invoking a test double, and a test whose name states an entry point it imports but never
calls. Scans every `test_*.py` under `[ledger] code_roots`, treating the packages and modules
found directly under those roots as the code under test. Candidates are for triage: the
command exits `0` and lists them in `--json`, and gating them is `keelline assess`'s. Refuses
(`2`) if its own self-test no longer discriminates. **Writes** nothing.

---

## Configuration

`keelline.toml` in the project root, committed. Every value is repository-controlled, which is
why so few of them are trusted with anything.

```toml
[keelline]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude", "codex"]

[project]
name = "widget"          # one lowercase path segment
base_branch = "main"
release_branch = "main"

[paths]
memory = "docs/memory"   # and the other document paths; each must stay inside the root

[memory]
mode = "local-only"      # local-only | in-repo | overlay
groups = ["developer", "project-stable", "project-volatile", "specs"]
index_extra = []         # extra pointers rendered into MEMORY.md

[budgets]                # a project may lower a preset's budget, never raise it
memory_index_words = 1200
startup_rules_words = 1600
volatile_notes_words = 2500
volatile_ttl_days = 30
```

`~/.config/keelline/config.toml` is yours, not the project's:

```toml
[personal]
reply_language = ""      # chat replies; durable artifacts stay in the artifact language
artifact_language = "en"

[overlay]
root = "~/keelline-overlay"   # only read in overlay mode
```

**This file's location is not selectable by a repository.** The path is
`~/.config/keelline/config.toml`, and neither `KEELLINE_CONFIG` nor `XDG_CONFIG_HOME` changes
it: a committed `.claude/settings.json` `env` block would otherwise choose your overlay root
and your trust record. Pass `--machine <path>` to read a different file — a path you typed
rather than one an environment chose, and honoured by every reader of it.

Only `[overlay]` and the trust record used to be held to that rule while `[personal]` followed
the environment, so one command could read the two halves of this file out of two different
files: `[personal]` honoured, and the overlay silently unrecorded a few lines below it.
