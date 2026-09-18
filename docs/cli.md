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
## Contents

- [`keelline memory index`](#keelline-memory-index)
- [`keelline memory trust --in-repo-memory`](#keelline-memory-trust---in-repo-memory)
- [`keelline memory session-context --bundle <name> [--part N]`](#keelline-memory-session-context---bundle-name---part-n)
- [`keelline memory inventory`](#keelline-memory-inventory)
- [`keelline memory fit`](#keelline-memory-fit)
- [`keelline release check`](#keelline-release-check)
- [`keelline hook <event>`](#keelline-hook-event)
- [Hooks](#hooks)
- [`keelline guard bg-cleanup`](#keelline-guard-bg-cleanup)
- [`keelline commit check --range RANGE`](#keelline-commit-check---range-range)
- [`keelline commit strip FILE`](#keelline-commit-strip-file)
- [`keelline test hygiene`](#keelline-test-hygiene)
- [`keelline test audit-entrypoints`](#keelline-test-audit-entrypoints)
- [`keelline bugs new TITLE --severity S --area A [--source S] [--related ID …] [--no-fetch]`](#keelline-bugs-new-title---severity-s---area-a---source-s---related-id----no-fetch)
- [`keelline bugs index [--check]`](#keelline-bugs-index---check)
- [`keelline bugs check`](#keelline-bugs-check)
- [`keelline bugs renumber OLD NEW`](#keelline-bugs-renumber-old-new)
- [`keelline docs check [--budgets] [--links] [--memory-graph] [--store PATH]`](#keelline-docs-check---budgets---links---memory-graph---store-path)
- [`keelline docs trail [--check]`](#keelline-docs-trail---check)
- [`keelline plan check [--base REF] [PATH …]`](#keelline-plan-check---base-ref-path-)
- [`keelline memory refs`](#keelline-memory-refs)
- [`keelline overlay create --owner OWNER [--name NAME] (--template | --local) [--root PATH]`](#keelline-overlay-create---owner-owner---name-name---template----local---root-path)
- [`keelline overlay init --owner OWNER [--root PATH]`](#keelline-overlay-init---owner-owner---root-path)
- [`keelline overlay upgrade [--root PATH] [--dry-run]`](#keelline-overlay-upgrade---root-path---dry-run)
- [`keelline attach --store PATH [--check] [--yes] [--trust-remote] [--root PATH] [--machine PATH]`](#keelline-attach---store-path---check---yes---trust-remote---root-path---machine-path)
- [`keelline detach [--root PATH] [--machine PATH]`](#keelline-detach---root-path---machine-path)
- [`keelline setup --preset NAME [--yes] [--home PATH] [--machine PATH] [--overlay VALUE] [--root PATH]`](#keelline-setup---preset-name---yes---home-path---machine-path---overlay-value---root-path)
- [`keelline setup --git-hooks [--uninstall] [--root PATH]`](#keelline-setup---git-hooks---uninstall---root-path)
- [`keelline doctor [--json] [--root PATH] [--home PATH] [--machine PATH]`](#keelline-doctor---json---root-path---home-path---machine-path)
- [Configuration](#configuration)

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

Exits `2` if `MEMORY.md` is a symlink this store may not follow (the target rule: outside
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
| `index` | `MEMORY.md` itself, so the model can route. **Emitted on Codex only**: Claude Code reads `MEMORY.md` natively, so injecting it there would spend capped `SessionStart` slots on something the harness already has. On any other harness this bundle prints nothing and exits `0`. The harness is read from this process's own environment, so the same command answers differently in a Codex session and a Claude Code one. |

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
continues with exit `0`. Either way the reason is written to stderr with a token — Codex
downgrades an exit `2` with empty stderr to a plain failure, so the reason is part of the
contract.

**Exit `2` is shared with the platform, and the wrapper does not pretend otherwise.** Because a
`2` the dispatcher produced is a deny that must pass through, a `2` CPython produced underneath
is indistinguishable from it and no token accompanies it. What the wrapper owns is the set of
faults it can reach *first* — a lost policy argument, no interpreter, a launcher it cannot read,
a project root it cannot enter — and each of those prints its token. So an exit `2` **carrying a
token** is attributed; an exit `2` carrying none is a handler's deny or a fault beneath the
wrapper, and `keelline doctor`'s `wrapper` row reports on the same basis.

| Token | What it means |
|---|---|
| `KL_ARGV` | The entry lost its policy argument. Always a refusal, whatever the missing policy would have been: a `closed` guard that disarmed itself must say so. |
| `KL_NO_PY` | No candidate interpreter is 3.11 or newer **and outside the project root**. The message distinguishes the two states, because their remedies differ: a candidate that was found inside the checkout and skipped says so and names the remedy, while "none among the candidates" means no interpreter answered at all. `KEELLINE_PYTHON_CANDIDATES` replaces the built-in list, space-separated — and is honoured **only when the wrapper's stdin is a terminal**, because it names the program the wrapper executes. See below. |
| `KL_NO_GIT` | There is no `git` at any of the wrapper's absolute candidate paths. `git`'s answer is one of the two anchors the interpreter containment is measured against, so a machine without one has no anchor this process can trust: it degrades under `open` and refuses under `closed`, rather than keeping the shape of the containment and none of its strength. `git` is **not** looked up on `PATH` here — see below. |
| `KL_NO_LAUNCHER` | There is no readable `scripts/keelline` beside the wrapper. The launcher is derived from the wrapper's own path and never read out of the environment: the harness substitutes the plugin root into the *command string*, so the wrapper that runs is always the plugin's own, while a variable of that name reaching this process from anywhere else would choose the program Python is handed — before any Keelline guard runs. Readability and not merely existence: a launcher at mode `000` otherwise reached CPython, which printed its own error and exited `2` with no token. |
| `KL_NO_ROOT` | `CLAUDE_PROJECT_DIR`, or `git`, named a project root the wrapper could not enter. A root that cannot be *resolved* is silent and correct — nothing is configured, so nothing is emitted — but a root that was named and cannot be entered used to leave the process in the harness's working directory, where every `--root`-defaulting entry would read whatever project happened to be there. |
| `KL_RC` | `keelline` exited with something other than `0` or `2`; the code is printed. |

**Which values may choose what.** The wrapper asks one question of everything it reads: is this
a *destination*, or does it choose a program, or the provenance of what runs? `CLAUDE_PROJECT_DIR`
is a destination and is honoured. `KEELLINE_PYTHON_CANDIDATES` is not — the probe asks a
candidate only to exit `0` for a trivial `-c`, so an unguarded list picks the interpreter that
runs on every tool call — and it is therefore gated where `keelline`'s machine configuration
gates `KEELLINE_CONFIG` and `XDG_CONFIG_HOME`: honoured from an interactive terminal, ignored
everywhere else. A hook's stdin is the harness's JSON payload on a pipe and `keelline doctor`
hands its own probe `/dev/null`, so a committed `.claude/settings.json` `env` block — which
applies without a trust prompt in a non-interactive session — cannot reach it, while a machine
owner debugging the probe by hand still can. The `git` that resolves the project root is asked
with an allowlisted environment for the same reason: an inherited `GIT_DIR` or `GIT_WORK_TREE`
otherwise made it answer for a different repository.

**`git` is chosen by the wrapper, not by `PATH`.** It answers the question the containment below
is measured against, and on the Codex path — where `CLAUDE_PROJECT_DIR` is unset — it is the only
anchor there is, so a bare `git` would let a clone that ships one have that binary executed on
every hook invocation, before any guard. The wrapper therefore tries a fixed list of absolute
paths and takes the first that exists, asking the machine owner's own installs before
`/usr/bin/git`; nothing under `$HOME` is on the list, because `HOME` is environment-chosen too.
A machine with `git` at none of them gets `KL_NO_GIT`. This is deliberately stricter than
`keelline`'s own `git` calls, which do resolve through `PATH` so that the machine owner's `git`
answers: those run inside a Keelline that has already chosen its interpreter, while this one
decides which programs may run at all.

**`PATH` is contained rather than trusted or dropped.** The last built-in candidate is bare
`python3`, resolved through `PATH`, and an `env` block can set `PATH` — so gating
`KEELLINE_PYTHON_CANDIDATES` alone would have moved the choice of program from one variable to
another. The entry cannot simply go: it is the fall-through the built-in list exists for, and a
machine whose Python lives under `pyenv`, `nix` or `asdf` has none at any of the four absolute
paths. So the rule is narrower and matches what a hostile clone can actually stage — **no
candidate whose resolved path lies inside the project root is used**, whatever spelling reached
it. Both sides are resolved before they are compared, so a relative entry, a `.` in `PATH`, a
`..` spelling and a symlink on either side all answer the same question. Where there is no
project root to compare against, the candidate stands.

**"The project root" here means either anchor.** `CLAUDE_PROJECT_DIR` and `git`'s answer are both
taken, and a candidate inside *either* is refused. Measured against `CLAUDE_PROJECT_DIR` alone
the rule was defeatable through the channel it exists to defeat: a clone that set `PATH` to its
own tree **and** named a root outside that tree made its own `python3` "outside the project
root". Against the pair, both anchors have to move at once, and one of them is now the answer of
a binary the clone does not choose. It is a union and not a check that the two agree, because a
disagreement rule has no answer where `git` returns nothing — every project that is not a git
repository — and its only fallback there is to trust the remaining variable on its own, which is
the same hole under a longer name.

A machine whose interpreter really is inside the checkout — a vendored toolchain, or an in-tree
virtual environment that is the only `python3` on `PATH` — gets `KL_NO_PY` rather than a silent
run of the tree's own program: a refusal under `closed`, a degradation under `open`, and a red
`wrapper` row in `keelline doctor` either way. That is the accepted cost of the rule, and it is
reached only when none of the four absolute candidates answers first.

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

**`--local` is the source that works today.** `--template` names
`<owner>/keelline-overlay-template`, and the command that publishes that repository —
`overlay publish-template`, a maintainer release action — has not shipped: it belongs with the
release lane that is its only caller. Until it does, `--template` fails cleanly for anyone who
has not created that repository on their own account by hand, and `--local` is what an owner
setting up a first overlay runs.

A template and not a fork: a fork's visibility is bound to the upstream network and cannot be
made private, which is the one outcome this command exists to prevent.

The `--template` path is idempotent, because `gh` can give up on the clone with the repository
already created: a directory that already carries `.claude-plugin/` is left alone and reported.
When `gh repo create` itself fails, the command stops there and reports **its** exit code and
**its** stderr: a `gh` that is not installed, or one that hung, costs one launch rather than
three, and the failure names the binary rather than sending you to `gh auth status` for a
repository that was never there. It also names the precondition above — the template repository
nothing publishes yet — because that is the usual reason this source cannot work. When `gh`
reports success and the clone brings nothing down, `gh repo view` is asked whether the repository
exists at all — the answer tells "not created" from "created, and the clone raced its generation"
— and the clone is retried once, after a ten-second wait when it was the second. **That retry is carried
on the strength of the design rather than of a measurement:** Findings → S6 did not reproduce
the race in the one trial it ran, and one clean run cannot rule out an asynchronous generation
step that sometimes outlasts a clone. If the second attempt is still empty, the command fails
(`1`) naming both attempts and what GitHub said in between.

**Writes** the instance directory and, on `--local`, every file of the template plus
`.keelline/manifest.json`. Exits `0` on success, `1` when no tree arrived, `2` on a refused name
or a missing `--root`.

---

## `keelline overlay init --owner OWNER [--root PATH]`

Makes a created overlay yours. It rewrites all three manifests — `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json` and `.codex-plugin/plugin.json` — so their names carry your
account (`keelline-overlay-octocat`, `keelline-overlay-marketplace-octocat`), because a harness
installs a plugin by the name in its manifest, and two owners' overlays under one configuration
directory would otherwise be one plugin fighting itself; the Codex half is included for the same
reason as the other two. The marketplace's own plugin entries are suffixed with it, so the
listing still names a manifest that answers. A manifest this overlay does not carry is reported
and skipped, not a failure.

Each rewrite is re-stamped into `.keelline/manifest.json`, so `overlay upgrade` still sees these
files as Keelline's own: without that, the file carrying `keelline.requires` read as hand-edited
from the moment you ran `init` and no release could ever refresh it again.

It then runs `pre-commit install` in the overlay, which is one of the two secret scans the
template ships; the other is the workflow that runs on every push, so `--no-verify` is not the
last word. `pre-commit` is optional: a missing or failing one is a reported note and never a
traceback.

Both halves are idempotent. A manifest that already carries the suffix is not rewritten, so a
second run reports nothing renamed.

**Writes** the three manifests and, where the overlay carries one, `.keelline/manifest.json` —
through the same contained walk every other write in this project goes through. Exits `0`; `1` on
a manifest that exists and cannot be read or is not JSON; `2` on an owner that is not one path
segment, or on a scaffold manifest that cannot be trusted.

---

## `keelline overlay upgrade [--root PATH] [--dry-run]`

**`--root` must name an overlay, and that is checked before anything is planned.** It defaults
to `.`, and pointed at a directory that is not one this command used to create the overlay's
fifteen files there — both plugin manifests, `hooks/hooks.json`, `.gitignore` and
`.github/workflows/scan.yml` among them — report them as work done and exit `0`. An overlay is a
tree whose two `.claude-plugin/` manifests name it `keelline-overlay[-<owner>]` and
`keelline-overlay-marketplace[-<owner>]`, which is what `overlay create` renders and `overlay
init` renames; anything else is refused (`2`) with nothing written.

Brings an overlay up to date with the template a newer Keelline ships. It is the project rule
and not a second copy of it: a skeleton file you have not touched is refreshed, one you have
edited is skipped and named, and the oracle is the digest `.keelline/manifest.json` recorded when
the file was written. An overlay is where your own rules live, so a silent overwrite here would
destroy the only copy of something.

**Two files are always listed, however their hashes compare.**
`common/claude/permissions.json` and `common/claude/hooks.json` are the two an overlay carries
that can grant a capability — a permission rule, a command that runs on an event — and a hash
that matches is not your consent to either. They are listed under `ASK FIRST` beneath the report,
and under `decisions` in `--json`. Without `--dry-run` that list is printed *after* the refresh,
not before it: nothing waits for an answer, and the reason it can be a notice rather than a gate
is that the shipped template grants nothing — its permissions file is deny-only and its hooks
file is empty, both held by a test. `--dry-run` first is how you read them before anything moves.

`--dry-run` prints the same report and writes nothing; the report you approve is produced by the
code path that then runs, which is what makes the dry run worth reading.

**Writes**, without `--dry-run`, every artifact the report lists as `create` or `update`, plus
`.keelline/manifest.json`. Exits `0`; `1` when the report carries a REFUSED section, because
nothing would be written while one of those stands; `2` when `--root` is not an overlay, when the
manifest itself cannot be trusted, or when a write is refused by the containment walk.

---

## `keelline attach --store PATH [--check] [--yes] [--trust-remote] [--root PATH] [--machine PATH]`

Binds this repository to your private overlay and links its note store in. After it, a session
in this repository reads your cross-project notes and this project's own notes, and the
permissions and hook entries you keep in the overlay are merged into
`.claude/settings.local.json`.

**`--machine` is honoured only from an interactive shell.** This is the command that turns the
machine configuration into capability: the overlay root comes from that file, and from the
overlay come allow rules, hook entries and standing rules. `KEELLINE_CONFIG` and
`XDG_CONFIG_HOME` are already gated the same way and for the same reason — a repository can set
an environment variable through a committed settings file, and it can just as easily tell an
agent to pass a flag. In a non-interactive session the flag is **refused** (`2`) rather than
ignored, because silently falling back would read your real configuration while the caller
believed it was reading the file it named. Omit it and the default file is read exactly as
before; `keelline detach` follows the same rule.

**`--store` names one directory and nothing else:** `<overlay>/projects/<project name>/memory`,
where `<project name>` is the `[project] name` in this repository's `keelline.toml`. The overlay
root itself is **not** taken from that path — it comes from the `[overlay] root` your machine
configuration records, which `keelline setup` writes. A `--store` anywhere else is refused (`2`),
including a directory elsewhere under the same overlay: the session-start path holds every linked
group to this project's own share, so attaching to a sibling would produce a store every session
then refuses.

**`--check` writes nothing.** It reports the binding state — `unbound`, `bound` or `mismatch` —
the permission diff (which allow rules and which hook entries would be added, and how many of
the overlay's rules this repository already has), and the Codex standing-rule files it would
place under `.codex/rules/`. Read it before the real run: everything under **Writes** below that
carries content from the overlay is named here first.

Those standing-rule files are reported but **not** gated by `--yes`. The gate is about widening
a *permission*; a standing rule is not one, and adding standing rules is the machine owner's own
to do — which is exactly what the overlay is. `widens` in the `--json` output therefore answers
about permissions alone, and `rules_to_write` lists the files.

**A write that grants a capability needs `--yes`.** If the diff would add an allow rule or a hook
entry, `attach` refuses (`2`) without it. That is a refusal and not a prompt on purpose: the
command line here is usually written by a model that has read this repository, so a gate whose
only enforcement is a step in a procedure is no gate at all. An overlay that grants nothing needs
no flag, because the gate is on the capability and not on the command.

**A mismatch needs `--trust-remote`.** The overlay records the remote it bound under this project
name; if this repository's `origin` is a different one, it is not the repository that was bound,
and `attach` refuses (`2`) unless you say otherwise. A clone chooses its own `project.name`; it
does not choose what the overlay recorded under that name.

**Reads** the overlay's `common/claude/permissions.json` and `common/claude/hooks.json`, this
project's `projects/<name>/claude/` equivalents, the overlay's `common/codex/` and
`projects/<name>/codex/` rules, and this repository's existing `.claude/settings.local.json`.
`.claude/settings.json` — the committed one — is read for **nothing**: it is repository-controlled,
and the repository never grants a capability.

**Writes** the `keelline:ignore` region in `.gitignore` (which is what keeps
`.keelline/local/` untracked, and is written first), `.claude/settings.local.json`,
`.codex/rules/`, the ledger `.keelline/local/attach.json`, the link tree under `paths.memory` in
this checkout and in every existing worktree, the harness memory link, and — in the overlay —
`projects/<name>/project.toml` and this project's note directories. The ledger is the only record
of which allow rules are Keelline's, because an allow rule cannot carry a marker the way a hook
entry can; `detach` reads it and nothing else.

It also **removes** one file, in one case. The `autoMemoryDirectory` fallback is taken only while
the harness memory link cannot be made, so when the link becomes possible again — or when the
store's trust record lapses — that key is withdrawn in the same run. If it was all
`.claude/settings.local.json` held, the file goes with it, because `{}` is not what that file
looked like before `attach` created it. Nothing you wrote is ever what goes: the case only
arises when Keelline's own key was the file's entire contents.

It also runs `pre-commit install` in the overlay when the overlay carries a pre-commit
configuration and no hook is installed — the machine that cloned an overlay someone else created
never ran `overlay init`. A missing `pre-commit` is a reported note, never a traceback.

Exits `0` on success, `1` on a mismatch under `--check`, `2` on a refusal: a store outside the
recorded overlay, a mismatch without `--trust-remote`, a widening without `--yes`, a checkout
with no `origin` remote, an existing `.keelline/local/attach.json` naming files or settings keys
`attach` could not have written, a `memory.groups` entry that leaves this project's share of the
overlay, or a `--machine` outside an interactive shell. Every one of those refusals happens
before the first write, so a refused attach leaves both the repository and the overlay as they
were. A write that itself fails also exits `2`, and is the one kind that can leave part of a run
behind: an unwritable `.gitignore`, or a path inside the overlay that is not a directory — or
became a symlink — between the moment it was checked and the moment it was written.

---

## `keelline detach [--root PATH] [--machine PATH]`

Removes exactly what `attach` added, and leaves the binding alone.

It reads `.keelline/local/attach.json` and acts on that and on nothing else *that it is willing
to believe*. A repository with no ledger fails (`1`) naming the missing file rather than guessing
which allow rules were Keelline's from their content — that guess is the reason the ledger
exists, and getting it wrong removes a rule you wrote by hand. And the ledger is not an
authority: `.gitignore` does not untrack a file a clone committed, so this path can arrive in a
fresh checkout with contents nobody on your machine wrote. Every field is held to what `attach`
could have put there — `rules` to a single file under `.codex/rules/`, `settings_keys` to
`autoMemoryDirectory` — and a ledger naming anything else is refused (`2`) with nothing removed,
rather than obeyed. A ledger claiming `settings_keys = ["permissions"]` would otherwise have
deleted your whole `permissions` block, deny rules included.

**Run it from the checkout you attached from.** `.keelline/local/` is untracked and per-checkout,
so a sibling worktree does not carry the ledger of the checkout the attach was run from and
`detach --root <that worktree>` answers "no ledger" — there is nothing there to reverse. Once it
starts it reaches every checkout of the repository, including the one that owns the store; it is
only the *starting* point that has to be the one holding the record.

**Writes**: it takes the recorded allow rules and the fallback key back out of
`.claude/settings.local.json`, drops the hook entries marked `# keelline:…` there (a group that
mixes one of those with your own entry is split, never replaced), removes the `.codex/rules/`
files it wrote, withdraws the link tree from this checkout and every worktree together with the
harness memory link, removes the `keelline:ignore` region, and deletes the ledger. A file left
holding nothing is removed rather than left empty.

**Directories come back too, with one exception.** `attach` records which of `.keelline/local/`,
`.keelline/`, `.codex/rules/`, `.codex/` and `.claude/` this repository did not have before it
ran, and `detach` removes exactly those, last, once everything inside them is gone. The removal
is `rmdir`: a directory still holding anything — your own `.codex/rules/` file, your
`.claude/settings.json` — survives, and so does its parent. A directory that was already there
before the attach is not on the record and is never touched.

The exception is the note link tree, ordinarily `docs/memory/` — **and the directory above it**,
`docs/`, which the attach creates in order to make it. That path is repository-configured and
may be one the project keeps for its own reasons, so the links are withdrawn and the directories
that held them are left, empty where there was nothing else in them. Everything else about the
round trip is byte-for-byte.

**It does not touch `projects/<name>/project.toml`.** That record is your consent to the binding,
not local state: deleting it would turn every later re-attach into a first attach and re-ask a
question you have already answered.

Exits `0`; `1` when there is no ledger to read; `2` on a ledger naming files or settings keys
`attach` could not have written, or on a `--machine` outside an interactive shell, for the
reason `keelline attach` gives above.

---

## `keelline setup --preset NAME [--yes] [--home PATH] [--machine PATH] [--overlay VALUE] [--root PATH]`

Configures this machine from a preset: the machine configuration file's
`[personal]` and `[machine]` tables, the deny rules and personal values in
`<home>/.claude/settings.json`, and the preset's plugins, one install per plugin per configured
harness. `--home` and `--machine` default to the home directory and to
`~/.config/keelline/config.toml` — the file every reader reads, and not whatever
`XDG_CONFIG_HOME` or `KEELLINE_CONFIG` names, because a machine file half the installation
cannot find is not a machine file. Both flags exist so this command can be pointed at a
scratch destination instead of your real one, the same way every other command here takes
`--root`. A scratch destination is **not a dry run**: the same files are written, at the paths
these two flags name, and nothing is suppressed. They apply to `--preset` alone — `--git-hooks`
writes inside a repository and ignores both.

`setup` is not the only command that writes outside a repository, and two others say so in their
own sections: `keelline memory trust` records approval in `~/.config/keelline/trust.json`, and
`keelline attach` places the harness memory link under `<home>/.claude/projects/`. It is the only
one that writes the machine configuration file and `<home>/.claude/settings.json`. `--root` (default `.`) is the project this invocation
was run from; the only thing it is used for is refusing an `--overlay` any checkout of it could
reach (below).

`setup` is the only writer of the machine configuration file, and the two existing readers do
not change: `[personal]` is `config.loader`'s, `[overlay] root` is `memory.store`'s, and both
still resolve the file `--machine` names or the default one. A second run merges rather than
replaces, key by key: a personal value already recorded — by an earlier `setup` or by your own
hand — is never overwritten by the preset's own default, and an overlay root a previous run
recorded survives a run that only changes something else. A table `setup` knows nothing about is
carried through untouched, and so is a key at the top level; **comments are not** — the file is
parsed and rewritten, and there is no standard-library parser that keeps them.

The `[personal]` values are mirrored into `pluginConfigs` in `<home>/.claude/settings.json`,
where Claude Code reads this plugin's own options, and that mirror is recomputed from the machine
file on every run. The machine file wins: a value you set in Claude Code's plugin-config UI is
overwritten by the next `setup`, because one of the two copies has to decide and the machine file
is the one everything in Keelline reads.

**Plugins are installed per configured harness**, from `[defaults.keelline] agents` (`claude`
and `codex` by default) and from the preset's own per-harness marketplace table
(`[plugins.<harness>]`). For each harness the preset declares a marketplace for, `setup`
registers it (`claude plugin marketplace add <source>`; idempotent — an already-registered
source is a no-op reported as such) and then installs each plugin bare (`claude plugin install
<name>@<marketplace>`; no `--scope` or `-y` — the spike record's own measured output reports
`(scope: user)` as the *default*, and `-y` only ever appears there on `uninstall`). Codex adds
rather than installs (`codex plugin add <name>@<marketplace>`) where the preset declares a
marketplace for it. A harness with no declared marketplace for a plugin is not attempted —
nothing here is vendored on a guessed marketplace name — and a missing binary or a
failed call is a reported note, never a failure.

**The overlay is touched only when `--overlay` names an answer**, and `--yes` does not imply
one. `--overlay <path>` records an existing overlay's root; `--overlay create:<owner>/<name>`
asks GitHub for a private repository from the template and initialises it, the same as
`keelline overlay create --template` followed by `overlay init` — and inherits that flag's
unshipped precondition, the template repository nothing publishes yet. Creating one needs `--yes` —
explicit confirmation for the one irreversible, outward-facing act this command performs — and
refuses (`2`) without it. Recording an *existing* path needs no `--yes`
(a model-written command line reaches `--overlay X --yes` exactly as easily as `--overlay X`,
so the flag would be theatre there); instead the path itself is validated **before the first
write** — before the machine file, the settings merge and the plugin installs, and for `create:`
before `gh repo create` runs on anybody's account. It must exist; its two `.claude-plugin/`
manifests must name it `keelline-overlay[-<owner>]` and `keelline-overlay-marketplace[-<owner>]`,
which is what `overlay create` renders and `overlay init` renames, rather than merely being
present; and it must lie outside the repository `--root` names — not inside it, not above it, and
not in another checkout of it, since a worktree is not a different repository and a clone ships
its tree into all of them. Where `git` cannot answer for `--root`, the path comparisons stand
alone.

**Writes** `--machine`'s file, `<home>/.claude/settings.json`, and — only with `--overlay` — the
new or recorded overlay itself. Exits `0` on success, `2` on a refused `--overlay` (missing,
not an overlay, reachable from the project root, or `create:` without `--yes`), and `2` when a
symlink stands between `<home>` and the settings file: that file is written through a walk that
never follows one. Every one of those refusals happens before the first write, **with one
exception**: for `--overlay create:<owner>/<name>`, "not an overlay" is a check on the tree that
arrived, so it runs after the repository has been created on GitHub and cloned — along with the
machine file, the settings merge and the plugin installs. That refusal says so, and names the
repository and where it was cloned to, because nothing else would. Everything else `create:` can
be refused for — the missing `--yes`, a malformed spec, a name that is not one path segment, a
destination the project root could reach — still happens before `gh` is run at all.

The symlink refusal names the link, where it leads, and a `keelline setup --home …` that writes
the file the link leads to — and where no `--home` can express the layout, it says that instead
of printing a command. `stow` folding a package to per-file links
(`~/.claude/settings.json -> <dotfiles>/claude/settings.json`) is that case: `--home H` writes
`H/.claude/settings.json` and nothing else, so no `H` names that target. Point the link at a
path ending in `.claude/settings.json`, or let this command write a real file and have your
dotfiles manager adopt it.

A plugin that fails to install or a harness that is absent is a note in the report, not a
nonzero exit.

---

## `keelline setup --git-hooks [--uninstall] [--root PATH]`

Installs the commit-message hook into this repository's own hooks directory — `git
rev-parse --git-path hooks`, never `core.hooksPath`, which is global state this command has no
business owning and which a repository-wide install would silently compete with husky or
`pre-commit` elsewhere on the machine.

A foreign hook of the same name is kept as `prepare-commit-msg.local` and the installed hook
`exec`s it last, so nothing that was already running there stops running; `--uninstall` puts it
back under its original name, byte for byte. The report names exactly what moved — a `.local`
file nobody was told about is indistinguishable from a lost one.

**Refuses (`2`) together with `--preset`.** The two write to different scopes — one repository,
one machine-wide — and a single invocation has only one exit code to report, so it does one of
the two.

**Writes** the hook file in `--root`'s hooks directory, and the `.local` file beside it only
when a foreign hook was there to preserve. Exits `0`; `2` when `--preset` is also given.

---

## `keelline doctor [--json] [--root PATH] [--home PATH] [--machine PATH]`

Fifteen checks over one installation. It **reports and never repairs**: every finding
carries the command that would fix it, and not one of them is run for you. Nothing is written.

**Several subprocesses are run and every one of them only asks.** Keelline's own
`hooks/run-hook.sh` with `--version`; `git ls-remote --exit-code` against the remote `[ci] ref`
names, only when one is set; and the `git` queries the other rows need — where the overlay keeps
its hooks, what its `origin` is, and where the note store resolves to. Four launches on a green
attached installation, measured. Exactly one of them, `ci-ref`, leaves this machine.

The summary line carries the counts and the names of whichever status most needs reading, capped
the way every summary in this CLI is. The rows are in `--json`, under `checks`, one object per
check with `name`, `status`, `detail` and `remedy`. A remedy that is not in `--json` is a remedy
nobody sees, so that is where they all are.

`status` is one of `ok`, `warn`, `red`, `skip`.

| Check | What it answers | What it reads |
|---|---|---|
| `not-initialised` | whether there is a `keelline.toml` here, and whether it loads | `keelline.toml` |
| `versions` | whether the project's `[keelline] version` is the Keelline running | `keelline.toml`, the package |
| `files` | the hook wrapper's executable bit, and the shipped files against the release's hashes | `hooks/run-hook.sh` |
| `wrapper` | whether the wrapper can actually reach Keelline on this machine | one `run-hook.sh open --version`, and only under the plugin root this Keelline is part of |
| `attached` | the overlay binding, and the shape of the harness memory path | `.keelline/local/attach.json`, `~/.claude/projects/<slug>/memory` |
| `hook-entries` | every hook entry, counted by provenance, with any that claims the Keelline marker and is in no ledger named by position | `.claude/settings.json`, `.claude/settings.local.json`, `.codex/hooks.json`, and `~/.claude/settings.json` |
| `codex-trust` | whether any Keelline hook is untrusted on Codex | — |
| `budgets` | every budget that overrides the preset, and every one the ceiling clamps | `keelline.toml`, the preset |
| `bundles` | a bundle that does not fit its slots, and one whose part reaches the cap | the note store |
| `cli-path` | whether `keelline` resolves on `PATH` | `PATH` |
| `pre-commit` | whether the overlay's commit-time secret scan is installed on this machine | the overlay |
| `ci-ref` | whether `[ci] ref` resolves | `git ls-remote --exit-code` |
| `store-debris` | files in the note store that are not notes | the note store |
| `diagnostics` | how many reasons the hook sink recorded — a count, never a line of the file | `${CLAUDE_PLUGIN_DATA}/keelline/diagnostics.jsonl` |
| `ignored-env` | `KEELLINE_CONFIG` or `XDG_CONFIG_HOME` set and not honoured | the environment |

**Eight of the fifteen have a `skip` arm: three always, and five more on a state of this
machine.** A `skip` is **not** a finding and never reaches the exit code, so read the detail —
each one says which measurement it is missing.

The three that skip on every correct installation are the ones this build cannot answer. `files` compares the installed
plugin against the release's recorded hashes, which the release lane ships — until then it
reports the wrapper's executable bit and skips the rest, because a check that compared a file
against itself would be worse than one that says it cannot. `codex-trust` needs the hash Codex
keys hook trust on, which no spike measured. `ci-ref` needs a `[ci] ref`, which `init` writes.

The five that skip on a state are `wrapper`, when there is no plugin root this process can
vouch for; `pre-commit`, when no overlay root is recorded on this machine; `bundles` and
`store-debris`, when the note store does not resolve; and `diagnostics`, when no harness data
root is set in the environment. `files` has a second skip arm for the same reason `wrapper` does.

**The one to read first is the plugin root**, because it is the quietest and the worst. When
this process can find no plugin root at all, `files` and `wrapper` both skip — two rows, no red,
and every hook entry on this machine silent. Both carry a remedy: run `keelline doctor` from the
plugin's own Keelline so its root answers for itself, or set `CLAUDE_PLUGIN_ROOT` to where the
plugin is installed, which lets `files` read the wrapper even though `wrapper` still will not
run it.

One more case is not a skip but produces fourteen of them: with no `keelline.toml` in `--root`,
or one that does not load, `not-initialised` goes **red** and every other check skips against it.
The red row is the one to act on.

**What is printed, and what is not. There is no exception.** Counts, statuses, file paths this
project chose and Keelline's own vocabulary print freely; a repository-authored string does not.
`[keelline] version`, `[ci] ref`, a note's filename, a hook's command text, the marker id an
entry claims, every field of the hook sink's diagnostics log and the reason the store would not
resolve are all read and none is quoted back — `keelline doctor --json` is relayed to a model
verbatim by the `doctor` skill, so a byte a repository wrote reaching this report is a byte
reaching the model outside `trust.wrap`.

`hook-entries` is where that bites, because its job is to list every entry with its provenance.
It identifies an entry **by position** — `.claude/settings.local.json entry 3 of 5` — which is
what a reader needs in order to open it, survives two entries claiming one id, and reproduces
nothing. A settings file that exists and cannot be read as hook entries is reported by path as
`warn`, never skipped: this is the one check whose whole purpose is that nobody's entries go
unlisted, so "all accounted for" must never mean "could not look".

`diagnostics` is the same ruling in the other direction, and is why that row counts rather than
quotes. Its three fields are Keelline's own vocabulary *for a log Keelline wrote*, and the log
is found through `${CLAUDE_PLUGIN_DATA}` — the same environment class a committed `env` block
reaches — so this command never establishes that. Refusing a marker id that a grammar bounds and
a cap limits, while printing an unbounded free-text `error` from a file of unknown provenance,
would not be a policy. The row reports how many failures are recorded and how many sessions were
seen, and the remedy names the file by its variable; you open it yourself.

**A plugin root the environment named is read and never run.** `wrapper` launches
`hooks/run-hook.sh` only under the root this Keelline derived from its own module path. With a
wheel installation there is no such root — which is what `uv tool install` gives, and what
`cli-path`'s own remedy suggests — and `CLAUDE_PLUGIN_ROOT` or `PLUGIN_ROOT` may then name one:
that root's wrapper is still read by `files`, for its executable bit, and `wrapper` reports
`skip` saying why. A report that ran a script the inspected repository could commit, and then
called the result green, would be worse than one that says it could not vouch for it.

**Writes** nothing. Exits `0`, or `1` when any check is red.

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
