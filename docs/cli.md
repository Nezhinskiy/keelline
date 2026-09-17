# Command reference

Every command, what it reads, what it writes, and what each exit code means. `keelline --help`
gives you the one-line version; this is the rest.

Three things hold everywhere:

- **`--json` is accepted anywhere** and prints one machine-readable object instead of one line.
  It is not declared per command — the frame strips it from `argv` before parsing. A command
  whose result is a list of findings carries it under **`findings`**, named after what the
  values are and spelled the same way by every command, whatever its summary line calls them.
  A list that is not findings keeps its own key: `docs check`'s advisory `notices`, and
  `docs trail`'s `written`, `undeclared` and `stale`.
- **Exit codes**: `0` success, `1` findings, `2` a refusal or an internal error. A caller that
  treats `1` as "proceed anyway" must still never treat `2` that way — a refusal is a boundary,
  not a low-confidence result.
- **Every `memory` command takes the same three options**, described once here rather than five
  times below. `--root` and `--machine` are not memory's alone: every `bugs`, `docs` and `plan`
  command takes them with the same meaning, and `docs check` takes `--store` as well.

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

## Hooks

The two harnesses do not run `keelline` directly. Every entry in `hooks/hooks.json` invokes
`hooks/run-hook.sh`, and its argv is:

```
run-hook.sh <policy> <keelline args…>
```

`<policy>` is `open` or `closed`, and it is the only argument the wrapper itself reads; the rest
is handed to `keelline` untouched. The wrapper exists because a Python process cannot fail
closed about its own absence: a missing script exits `2` by CPython accident, a missing
interpreter `127`, an `ImportError` `1`, a lost executable bit `126` — and Claude Code reads
every exit that is not `2` as a non-blocking error, which is permission. So the wrapper owns
three things Python cannot: it probes for a `python3` of 3.11 or newer by running code rather
than by matching a path, it resolves the project root (`CLAUDE_PROJECT_DIR`, else `git`) and
changes into it so every command's `--root` default is correct, and it maps exit codes.

`0` and `2` are the dispatcher's own and pass through untouched — a `2` it produced is a
handler's deny, not a wrapper failure. Every other exit code, and every fault the wrapper finds
before `keelline` runs at all, is judged by `<policy>`: `closed` refuses with exit `2`, `open`
continues with exit `0`. Either way the reason is written to stderr with a token, so an exit `2`
is attributed rather than inferred — Codex downgrades an exit `2` with empty stderr to a plain
failure, so the reason is part of the contract.

| Token | What it means |
|---|---|
| `KL_ARGV` | The entry lost its policy argument. Always a refusal, whatever the missing policy would have been: a `closed` guard that disarmed itself must say so. |
| `KL_NO_PY` | No candidate interpreter is 3.11 or newer. `KEELLINE_PYTHON_CANDIDATES` overrides the built-in list, space-separated; it exists for the tests and for nothing else. |
| `KL_NO_LAUNCHER` | `CLAUDE_PLUGIN_ROOT` is unset, or `scripts/keelline` is not there. |
| `KL_RC` | `keelline` exited with something other than `0` or `2`; the code is printed. |

**The one row this does not cover.** A `run-hook.sh` whose executable bit has been cleared is
never executed by the harness at all, so no code of ours runs and no policy applies — the guard
is silent rather than closed. The wrapper cannot defend its own mode, and nothing in this
build catches it: `keelline doctor`, whose wrapper probe is the answer to it, does not ship
yet. Until it does, `ls -l` on the file is the whole of the check.

## `keelline guard bg-cleanup`

Judge one Bash call for a background leak. Reads one JSON object on stdin — a whole hook
payload, or a bare `tool_input` with `command` and `run_in_background` — and answers `2` when
the call would be refused (a `&`-backgrounded job with no `trap … EXIT`, or a backgrounded
command that begins with `sleep`), `1` when it carries a trailing restore no trap protects or,
for a backgrounded call, ends in a `; echo …` that hides the exit code the completion
notification will report, and `0` otherwise. Both refusals need `run_in_background` to be
`true` in the object you send —
the leak and the `sleep` are only faults for a job the harness will not reap, so a CI smoke
test written without that key measures `0` on a command that is refused in a session.
Anything it cannot read is `2`: this is the fail-closed row of the CLI table, and a guard that
guessed would be guessing. That is about the JSON, not about the command inside it: a command
longer than the 64 KiB cap is not read either, and is allowed (`0`) rather than refused,
because tokenizing an unbounded string in front of every Bash call is the larger fault.

This is the same judgement the `PreToolUse` `Bash` hook makes; the command exists so a CI
smoke test and a person can ask it without a harness. **Writes** nothing.

## `keelline commit check --range RANGE`

Every message in `RANGE` (a `git log` revision range, e.g. `main..HEAD`), for lines in its
trailing attribution block that are an AI/tool attribution trailer or footer: a `-by:` trailer
whose address is at a vendor's domain or whose name is a product, a `Generated with <tool>`
footer, or a line that is only `AI-generated`. The block is the message's last paragraph plus
every paragraph above it that is attribution to the last line — the canonical harness block is
two paragraphs — and it ends at the first paragraph holding any body line. Body prose is never
judged, and a person whose name happens to be a vendor word is not a violation.
`[commit_messages] attribution_check = false` stops the rules being applied: no message is ever
a violation, but the range must still be readable, because the report says how many messages it
read. Exits `1` naming each offence as `sha line N [label]` — never the text, which is the
repository's — and `2` when git cannot read the range or the range looks like an option.
**Writes** nothing. This is what the reusable workflow runs.

Exit `1` has two meanings here and a gate should know both: messages were read and some carry a
trailer (`FAIL: …`), and *no `keelline.toml` was found under `--root`*, which the configuration
loader reports as a failure — `keelline: failed: …/keelline.toml does not exist` — and not as a
refusal. A workflow that must tell them apart reads the first word of the output, or checks the
file is there before it runs the gate.

## `keelline commit strip FILE`

Rewrite a commit-message file in place with the attribution lines of its trailing attribution
block removed — never a line of the body. Exits `0` whether or not anything was stripped, and
says which; a message that is *only* attribution is left alone, because emptying it aborts the
commit with a confusing error and CI explains better. Refuses a symlink, and fails (`1`) on a
file it cannot read, a file that is not UTF-8 included.

Git's own trailing comment block is kept, and so is everything below the scissors line that
`commit.verbose = true` puts the staged diff under — the message is what lies above both.

This is what the chained `prepare-commit-msg` hook runs, so the trailer is gone before the
commit exists; `git commit --no-verify` skips `commit-msg` but not that hook. Installing the
hook is a library call today (`keelline.guards.api.install`) — no `keelline` subcommand offers
it yet. **Writes** `FILE`.

## `keelline test hygiene`

The two environment faults that make a red test run unattributable: uncommitted changes in
the tree, and `.pyc` files whose recorded source mtime no longer matches their source. Counts
the bytecode under `[ledger] code_roots` and the uncommitted changes across the whole
repository — a dirty tree anywhere makes a red run unattributable — and exits `1` when either
is present, `2` when git cannot report the tree. The `PostToolUse` `Bash` hook delivers the
same note once per context after a red pytest run. **Writes** nothing.

## `keelline test audit-entrypoints`

Tests that never exercise what they name, in two shapes: an assertion whose value is produced
by invoking a test double, and a test whose name states an entry point it imports but never
mentions again, in its own body or in the local helpers it reaches. Scans every `test_*.py`
under `[ledger] code_roots`, treating the packages and modules found directly under those
roots as the code under test. Candidates are for triage: the command exits `0` and lists them in
`--json`, **with findings and no way to fail on them** — that is deliberate, not an oversight,
and nothing here gates. Run over a repository's own suite the scanner names name-collision
candidates that are not defects, so an exit `1` would be red from the first run, and the
configuration has no per-command switch to turn it off with. Gating belongs to a lane that has
triaged them to zero, and that lane has not shipped. Refuses (`2`) if its own self-test no
longer discriminates. **Writes** nothing.

The `--json` object carries `summary` (the line the command would have printed), `files` (how
many test files were scanned), `import_roots` (the
top-level names treated as the code under test) and `findings`, sorted by path then line. Each
finding is `path`, `line`, `test` (the test function's name), `shape` (`assert-on-double` or
`names-but-never-invokes`) and `detail`. These keys are the contract; `path`, `test` and
`detail` are repository-authored strings, which is why they are in `--json` and not in the
summary line.

## `keelline bugs new TITLE --severity S --area A [--source S] [--related ID …] [--no-fetch]`

File a bug: allocate the next free identifier (`1 + max` over every entry in the working tree
and every entry ever added on any ref, after a bounded `git fetch origin` unless `--no-fetch`),
write `<paths.bugs>/<PREFIX>-nnn.md` from the template, and regenerate the index. Every
rejection happens before the first write: a title or source the flat frontmatter subset cannot
hold is quoted for you; a `--related` value that is not an identifier, an index carrying content
this tool did not generate (`2`), and an allocated identifier whose file already exists (`1`,
naming `bugs check`) each leave the tree exactly as it was. A skipped fetch is reported on the
result line, not hidden. **Writes** the entry file and `<paths.bug_index>`.

## `keelline bugs index [--check]`

Render `<paths.bug_index>` from the entry files alone. `--check` exits `1` when the committed
index differs from that rendering and writes nothing. Either form refuses (`2`) while the write
would destroy something: a line the index holds that this tool did not generate (a hand-written
section, an operator's note, or a table row with no entry file behind it — recover it into an
entry file first), or a generated index whose entry directory is gone (restore the files; the
index carries nothing of its own). A row is judged by the entry it links and not by its shape,
so a row whose entry file went missing in a merge — the last record that bug existed — is not
something regenerating may delete. A reworded
header is a stale index, not foreign content. The first paragraph names the generator, and that
paragraph is recognised structurally rather than by an exact string, so an index left by an
older generated format is still read as generated rather than refused as hand-written content.
**Writes** `<paths.bug_index>`.

## `keelline bugs check`

Every rule the ledger holds, in one pass: each entry parses under the flat frontmatter subset
and its `id:` matches its filename; no entry restates `**Status:**`/`**Severity:**` in its
body; every severity in `[ledger] evidence_boundary_required_for` carries a filled `**What this
evidence does not establish:**` line (the template's placeholder does not count); no identifier
is claimed by two files; every `related:` identifier has an entry; the index carries nothing
this tool did not generate, and is current; every `<PREFIX>-nnn` mentioned under the top-level
files and `[ledger] code_roots` has an entry (a `void` entry counts); every citation of an entry
*file* — from those roots and from the directories the `[paths]` values live under — names a
file that exists. Exits `1` with the count and up to eight `path:line [rule]` labels on the
line; `--json` carries every finding with its `detail`, which may quote the repository and is
why it is not on the line. Before a ledger exists — no `[paths] bugs` directory *and* no
generated index — prints `nothing to check` and exits `0`; a generated index with no directory
behind it is a deleted ledger and exits `1`. Git enumerates the files where the root is the top
of a checkout (tracked plus untracked-not-ignored), and a walk stands in elsewhere. A file whose
first 2 KiB carry `keelline:ledger:fixtures` holds sample identifiers and is neither scanned nor
swept. **Writes** nothing.

## `keelline bugs renumber OLD NEW`

Move an entry to a free identifier: `NEW` gets the entry with its `id:` rewritten, `OLD` becomes
a `void` pointer at the new number, every scanned file that mentions `OLD` is rewritten, and the
index is regenerated — both endpoints first, then the sweep, so an interruption leaves `OLD`
resolving to the pointer rather than to nothing. Rejects an occupied `NEW` or a missing `OLD`
(`1`) and raises the index refusals of `bugs index` (`2`) before touching anything. A file the sweep
could not read or write is listed and the command exits `1` naming it, because once the pointer
exists a stale mention in that file looks intentional to `bugs check` forever. The moved entry's
own body is the operator's to rewrite and is not swept. **Writes** the two entry files, every
rewritten file, and `<paths.bug_index>`.

## `keelline docs check [--budgets] [--links] [--memory-graph] [--store PATH]`

Two kinds of check, and the difference is the whole design; no flag runs the enforced
two, and `--memory-graph` is opt-in. **Enforced** (exit `1`, `FAIL:`):
the always-loaded document at `[paths] agents_md` exists, is within `agents_md_lines` and
`agents_md_words`, and has a `## Current status` section within `status_lines`; the roadmap at
`[paths] roadmap`, up to the line `## Design and plan trail`, is within `roadmap_prose_lines`
and `roadmap_prose_words` (a roadmap with no marker is budgeted whole; an absent one is not a
finding); every relative local link in the agents file resolves to a file — read from that
document's own directory, and only when it lands inside the project root, since a link that
walks out through `..` would be settled against the machine rather than the repository (an
absolute link is not read at all, nor is an anchor, a URL or a `mailto:`). Budgets are the
effective ones — the preset's, lowered by `[budgets]` if the project chose to. **Advisory**
(`--memory-graph`; exit `0` always): over the resolved memory store, every `[[wiki-link]]`
names a document in the store, no link is immediately repeated, and no ledger identifier is
bracketed; reported as `notices` in `--json` and counted on the line, which never vouches for
the store. Silent where no store resolves. **Writes** nothing.

## `keelline docs trail [--check]`

Rewrite the listing between `## Design and plan trail` and `<!-- end design and plan trail -->`
in the roadmap: every `*.md` under `[paths] specs` and `[paths] plans` that git tracks and does
not ignore, grouped by the first `[[theme]]` in `trail.toml` (beside the roadmap) whose
`pattern` matches its filename, `Unfiled` otherwise, each annotated with its `[states]` entry or
`delivered`. `--check` exits `1` when the listing is stale and writes nothing. Two guards make
the listing unable to lie by silence: a state naming a document that no longer exists fails
(`1`) before anything is written, and a document that enters the listing without a declared
state is written as `delivered` and then reported (`1`) — a design is written before the thing
is built. That second guard fires on the writing path only: a row enters the listing through
`docs trail`, whose exit `1` the operator sees, and `--check` has no earlier listing to compare
against, so a defaulted `delivered` that was committed over that report is invisible to CI.
A `trail.toml` outside its contract fails (`1`): a non-string label, a pattern that does not
compile, a file that is not valid UTF-8, or a `label` or `[states]` value that is not a single
line or that carries either marker — both are written into the listing verbatim, so one could
otherwise split the block and push repository prose into the roadmap. **Writes**
`[paths] roadmap`.

## `keelline plan check [--base REF] [PATH …]`

With `PATH` arguments, lint exactly those plans; without, the plans under `[paths] plans` that
`REF...HEAD` touches, `REF` defaulting to `origin/<project.base_branch>`. Four rules, each from a
retrospective: every backticked path resolves unless the line says `(create)` or declares it
on a `Create:`/`Test:` line; no step is phrased as already knowing its answer (`confirm that
nothing …`, `verify no …`, `check that it does not …`); a `**Scope:**` line with content is
present; a plan claiming `Fixes <PREFIX>-nnn` carries a `**Premise:**` line with content; and a
mutation's outcome stated as fact in the present tense (`-> the test reddens`, `watch it go
red`, `reddens 8 assertions`) is a finding unless its own sentence marks it an expectation.
Fenced code is fixture text, and so is a path claim that lands outside the project root —
an absolute one, or one that walks out through `..` — which is never settled against the
filesystem, because that answer would be about the machine rather than about the repository. A
base that does not resolve is a finding (`1`), never an OK: in CI the cause is a checkout too
shallow to hold the ref (`fetch-depth: 0`). A `REF` shaped like an option is refused (`2`)
before git sees it. Uncommitted plans
are not in the diff; the line counts them and `--json` names them, and naming one as `PATH`
lints it. **Writes** nothing.

## `keelline memory refs`

Every backticked repository path a note names still exists. Notes are read as authoritative and
age silently, so a path to a deleted module sends the next session after it. A candidate is
dropped when the tree explains it: shorthand that resolves under the root, a code root or the
directory a `[paths]` value lives in; an absolute path outside the repository; a placeholder
(`scripts/foo.py`); a path the repository's ignore rules cover — except a path into the store
itself, which those rules cover wholesale and which is settled on disk. Fenced code and bare
filenames are skipped. In an overlay store, a note in a cross-project group that `[[links]]`
into a project-scoped note is an `audience` finding. Exits `1` listing `note:line [rule]`; the
targets are in `--json`. A note that exists and would not parse is counted on the line and
named in `--json`, and is exit `1` too: an unread note is not a clean note. Refuses (`2`) when a
configured group could not be resolved, naming each group and carrying the resolver's own reason
for it inside the delimited region that marks repository-authored text as data — because a walk
over a subset that reports nothing stale is worse than no guard. Where *no* store resolves at
all, the exit is `1`: that comes from the resolver every `memory` command shares, so part of the
store being unreadable is a refusal while the whole of it being unreadable is findings. That is
the wrong way round by the ordering above, it is a known issue the memory lane owns, and until
it is fixed a caller should gate on a non-zero exit rather than on the number. Write a path that
deliberately does not resolve in *italics*. **Writes** nothing.

---

## `keelline overlay create --owner OWNER [--name NAME] (--template | --local) [--root PATH]`

Creates the private overlay: the repository that holds your standing rules, your cross-project
notes, and one record per repository bound to them. Nothing in it is any project's, which is why
it is a repository of its own and why it is private.

`--owner` is the account it belongs to and `--name` the repository name (default
`keelline-private`). Both are held to one path segment matching `[a-z0-9][a-z0-9._-]*`, because
each becomes a directory name, half a remote path and later a marketplace selector; a value
shaped like an option is refused rather than quoted. `--root` is the directory the instance is
created *in*, not a project root, and defaults to the current directory.

**Neither source is a default.** `--template` asks GitHub to generate a private repository from
your template repository and clone it; `--local` renders the shipped template here and makes no
network call. An invocation with neither is refused (`2`) naming both, so that creating a
repository on an account is never something an omitted flag does.

A template and not a fork: a fork's visibility is bound to the upstream network and cannot be
made private, which is the one outcome this command exists to prevent.

The `--template` path is idempotent, because `gh` can give up on the clone with the repository
already created: a directory that already carries `.claude-plugin/` is left alone and reported.
When the clone brings nothing down, `gh repo view` is asked whether the repository exists at all
— the answer tells "not created" from "created, and the clone raced its generation" — and the
clone is retried once, after a ten-second wait when it was the second. **That retry is carried
on the strength of the design rather than of a measurement:** Findings → S6 did not reproduce
the race in the one trial it ran, and one clean run cannot rule out an asynchronous generation
step that sometimes outlasts a clone. If the second attempt is still empty, the command fails
(`1`) naming both attempts and what GitHub said in between.

**Writes** the instance directory and, on `--local`, every file of the template plus
`.keelline/manifest.json`. Exits `0` on success, `1` when no tree arrived, `2` on a refused name
or a missing `--root`.

---

## `keelline overlay init --owner OWNER [--root PATH]`

Makes a created overlay yours. It rewrites the plugin and marketplace manifests so their names
carry your account — `keelline-overlay-octocat`, `keelline-overlay-marketplace-octocat` — because
a harness installs a plugin by the name in its manifest, and two owners' overlays under one
configuration directory would otherwise be one plugin fighting itself. The marketplace's own
plugin entries are suffixed with it, so the listing still names a manifest that answers.

It then runs `pre-commit install` in the overlay, which is one of the two secret scans the
template ships; the other is the workflow that runs on every push, so `--no-verify` is not the
last word. `pre-commit` is optional: a missing or failing one is a reported note and never a
traceback.

Both halves are idempotent. A manifest that already carries the suffix is not rewritten, so a
second run reports nothing renamed.

**Writes** `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, through the same
contained walk every other write in this project goes through. Exits `0`; `1` on a manifest that
cannot be read or is not JSON; `2` on an owner that is not one path segment.

---

## `keelline overlay upgrade [--root PATH] [--dry-run]`

Brings an overlay up to date with the template a newer Keelline ships. It is the project rule
and not a second copy of it: a skeleton file you have not touched is refreshed, one you have
edited is skipped and named, and the oracle is the digest `.keelline/manifest.json` recorded when
the file was written. An overlay is where your own rules live, so a silent overwrite here would
destroy the only copy of something.

**Two files are always asked about, however their hashes compare.**
`common/claude/permissions.json` and `common/claude/hooks.json` are the two an overlay carries
that can grant a capability — a permission rule, a command that runs on an event — and a hash
that matches is not your consent to either. They are listed under `ASK FIRST` beneath the report,
and under `decisions` in `--json`.

`--dry-run` prints the same report and writes nothing; the report you approve is produced by the
code path that then runs, which is what makes the dry run worth reading.

**Writes**, without `--dry-run`, every artifact the report lists as `create` or `update`, plus
`.keelline/manifest.json`. Exits `0`; `1` when the report carries a REFUSED section, because
nothing would be written while one of those stands; `2` when the manifest itself cannot be
trusted, or when a write is refused by the containment walk.

---

## Configuration

`keelline.toml` in the project root, committed. Every value is repository-controlled, which is
why so few of them are trusted with anything.

```toml
[keelline]
version = "0.1.0"        # required; there is no default
state = "installed"      # initialised | adopting | installed — default: initialised
preset = "recommended"
profile = ""
agents = ["claude", "codex"]

[project]
name = "widget"          # one lowercase path segment
base_branch = "main"
release_branch = "main"

[paths]                  # each must stay inside the root
agents_md = "AGENTS.md"
architecture = "docs/architecture"
runbooks = "docs/runbooks"
adr = "docs/adr"
specs = "docs/specs"
plans = "docs/plans"
bugs = "docs/bugs"
bug_index = "docs/bug-reports.md"
roadmap = "docs/roadmap.md"
roadmap_history = "docs/roadmap-history.md"
memory = "docs/memory"

[memory]
mode = "local-only"      # local-only | in-repo | overlay
groups = ["developer", "project-stable", "project-volatile", "specs"]
index_extra = []         # extra pointers rendered into MEMORY.md

[ledger]
id_prefix = "BR"         # a capital letter, then up to seven more capitals or digits
code_roots = ["src", "tests", "scripts"]
evidence_boundary_required_for = ["high"]

[budgets]                # a project may lower a preset's budget, never raise it
agents_md_lines = 300
agents_md_words = 3000
status_lines = 50
roadmap_prose_lines = 350
roadmap_prose_words = 3500
memory_index_words = 1200
startup_rules_words = 1600
volatile_notes_words = 2500
volatile_ttl_days = 30
```

Every value above is what a key you leave out takes, from the `recommended` preset — with two
exceptions, and one line that is an example rather than a default. `[keelline] version` and
`[project] name` have no default at all and are yours to write: a file without `version` does
not load at all (`[keelline] is missing required key(s): version`). And `[keelline] state`
defaults to `initialised` — it is one of `initialised`, `adopting` and `installed`, and the
`installed` above shows a set value, not what an omitted key takes. Everything from
`[project] base_branch` down, `[paths]`, `[memory]`, `[ledger]` and `[budgets]` included, is the
preset's default exactly as written.

**Which command reads which path.** `agents_md` and `roadmap` are the two documents `docs check`
budgets, and the roadmap is also what `docs trail` writes into; `specs` and `plans` are the two
trees `docs trail` lists, and `plans` is where `plan check` looks for the plans a diff touched.
`bugs` is the ledger's entry directory and `bug_index` its generated index — `bugs new`,
`bugs index`, `bugs check` and `bugs renumber` all read both — and `runbooks` supplies the
`<runbooks>/bug-reports.md` link that index's generated header writes. `memory` is the note
store, which `memory refs` walks. The remaining three are read for their location alone, and so
is every one of the others: `bugs check` treats the first component of every `[paths]` value
that has more than one — `docs`, for the defaults — as a directory documents live in, and
therefore as a place a citation of an entry file may be written and must resolve. Pointing a
path key somewhere unusual widens that sweep; it cannot take a document outside it, because a
value that leaves the root is refused before any command runs.

**`[ledger]`.** `id_prefix` is the one definition of what an identifier looks like: `BR-001`,
and `BR-nnn` in every message. It is interpolated into patterns and filenames, so it is held to
a shape — a capital letter followed by up to seven more capitals or digits — and a prefix
outside it is a refusal (`2`), not a finding. The number is three digits or more. `code_roots`
are the trees `bugs check` sweeps for mentions of an identifier, each of which must have an
entry behind it; `evidence_boundary_required_for` names the severities whose entries must carry
a filled `**What this evidence does not establish:**` line, the template's placeholder not
counting. Widening it is how a project asks the same of `medium`.

**The two ledger vocabularies**, neither of them configurable — they are the entry contract, and
a value outside either is a finding (`1`) naming the file:

| Field | Values |
|---|---|
| `status:` | `open`, `partial`, `fixed`, `rejected`, `void` |
| `severity:` | `high`, `medium`, `low` |

`void` is the one that is not a state of a bug: it records a number that was allocated and never
carried one — what `bugs renumber` leaves behind at the old identifier — and it is the only
status that needs neither `severity:` nor `area:`. `severity` is `bugs new`'s required
`--severity`, and `--area` beside it is free text that becomes the entry's Area column.

**`[budgets]`.** The first five are the documentation budgets `docs check` enforces:
`agents_md_lines`, `agents_md_words` and `status_lines` over the always-loaded document and its
`## Current status` section, `roadmap_prose_lines` and `roadmap_prose_words` over the roadmap
above its trail marker. The last four bound the memory store. A budget is only ever lowered: a
value above the preset's is ignored rather than refused, so raising one is not an escape.

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
