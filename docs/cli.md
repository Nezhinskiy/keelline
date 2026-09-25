# Command reference

Every command, what it reads, what it writes, and what each exit code means. `keelline --help`
gives you the one-line version; this is the rest.

Three things hold everywhere:

- **`--json` is accepted anywhere** and prints one machine-readable object instead of one line.
  It is not declared per command — the frame strips it from `argv` before parsing. A command
  whose result is a list of findings carries it under **`findings`**, named after what the
  values are and spelled the same way by every command, whatever its summary line calls them.
  Five commands do: `bugs check`, `docs check`, `memory refs`, `plan check` and
  `test audit-entrypoints`. Every other command's keys are its own and are listed with it
  below — `doctor`'s `checks`, `docs check`'s advisory `notices`, `docs trail`'s `undeclared`,
  and the two of `docs trail`'s keys that are not lists at all, `written` and `stale`.
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
- [`keelline release check [--tag TAG]`](#keelline-release-check---tag-tag)
- [`keelline release notes --version X.Y.Z [--draft]`](#keelline-release-notes---version-xyz---draft)
- [`keelline release hashes [--check]`](#keelline-release-hashes---check)
- [`keelline hook <event>`](#keelline-hook-event)
- [Hooks](#hooks)
- [`keelline guard bg-cleanup`](#keelline-guard-bg-cleanup)
- [`keelline commit check --range RANGE`](#keelline-commit-check---range-range)
- [`keelline commit strip FILE`](#keelline-commit-strip-file)
- [`keelline test hygiene`](#keelline-test-hygiene)
- [`keelline test audit-entrypoints`](#keelline-test-audit-entrypoints)
- [`keelline test attribute --command CMD [--base REF]`](#keelline-test-attribute---command-cmd---base-ref)
- [`keelline bugs new TITLE --severity S --area A [--source S] [--related ID …] [--no-fetch]`](#keelline-bugs-new-title---severity-s---area-a---source-s---related-id----no-fetch)
- [`keelline bugs index [--check]`](#keelline-bugs-index---check)
- [`keelline bugs check`](#keelline-bugs-check)
- [`keelline bugs renumber OLD NEW`](#keelline-bugs-renumber-old-new)
- [`keelline docs check [--budgets] [--links] [--memory-graph] [--store PATH]`](#keelline-docs-check---budgets---links---memory-graph---store-path)
- [`keelline docs trail [--check]`](#keelline-docs-trail---check)
- [`keelline plan check [--base REF] [PATH …]`](#keelline-plan-check---base-ref-path-)
- [`keelline memory refs`](#keelline-memory-refs)
- [`keelline init --yes [--dry-run] [--no-ci] [--root PATH] [--machine PATH]`](#keelline-init---yes---dry-run---no-ci---root-path---machine-path)
- [`keelline upgrade [--dry-run] [--force PATH]… [--root PATH] [--machine PATH]`](#keelline-upgrade---dry-run---force-path---root-path---machine-path)
- [`keelline uninstall [--dry-run] [--force PATH]… [--root PATH] [--machine PATH]`](#keelline-uninstall---dry-run---force-path---root-path---machine-path)
- [`keelline overlay create --owner OWNER [--name NAME] (--template | --local) [--root PATH]`](#keelline-overlay-create---owner-owner---name-name---template----local---root-path)
- [`keelline overlay init --owner OWNER [--root PATH]`](#keelline-overlay-init---owner-owner---root-path)
- [`keelline overlay upgrade [--root PATH] [--dry-run]`](#keelline-overlay-upgrade---root-path---dry-run)
- [`keelline overlay publish-template --owner OWNER [--name NAME] [--yes]`](#keelline-overlay-publish-template---owner-owner---name-name---yes)
- [`keelline attach --store PATH [--check] [--yes] [--trust-remote] [--root PATH] [--machine PATH]`](#keelline-attach---store-path---check---yes---trust-remote---root-path---machine-path)
- [`keelline detach [--root PATH] [--machine PATH]`](#keelline-detach---root-path---machine-path)
- [`keelline setup --preset NAME [--yes] [--home PATH] [--settings PATH] [--machine PATH] [--overlay VALUE] [--root PATH]`](#keelline-setup---preset-name---yes---home-path---settings-path---machine-path---overlay-value---root-path)
- [`keelline setup --git-hooks [--uninstall] [--root PATH]`](#keelline-setup---git-hooks---uninstall---root-path)
- [`keelline doctor [--json] [--root PATH] [--home PATH] [--machine PATH]`](#keelline-doctor---json---root-path---home-path---machine-path)
- [The reusable workflow](#the-reusable-workflow)
- [Shared flags](#shared-flags)
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

Record that the notes sitting inside this repository may reach the model.

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

## `keelline release check [--tag TAG]`

Cross-checks the version across `pyproject.toml`, `uv.lock`, `src/keelline/__init__.py`, both
plugin manifests and `CHANGELOG.md`. Exits `1` naming every source that disagrees.

The `--json` object carries `summary`, `versions` (every source and what it says) and
`problems` (empty on a clean run), and it carries all three **whether or not there is drift** —
the drift is in `problems`, not in the shape. A source this gate cannot parse at all is still a
refusal and prints `error` instead, which is the difference between a finding and a failure.

`--tag` adds the tag as a further source, and it is what the release workflow runs. Both tag
shapes are accepted — `vX.Y.Z`, which is the workflow's trigger, and the platform's own
`keelline--vX.Y.Z` — because either may be the ref a run was created from. Under `--tag` one
other rule tightens: without it a pending fragment in `changelog.d/` lets `CHANGELOG.md` lag,
because a lane writes its fragment long before a release assembles it, but at a tag there is
nothing left to assemble, so a fragment still pending means the changelog users will read is
not the one the tag claims. That is a finding naming the count.

This is discipline for **the Keelline repository itself**, not something Keelline offers your
project. See [RELEASING.md](../RELEASING.md).

## `keelline release notes --version X.Y.Z [--draft]`

Assemble `CHANGELOG.md` from the fragments in `changelog.d/`, through towncrier.

```bash
keelline release notes --version 1.2.3 --draft   # print the section; write nothing
keelline release notes --version 1.2.3           # write it, and consume the fragments
```

A wrapper and nothing more: towncrier does the rendering and `[tool.towncrier]` in
`pyproject.toml` owns the format. Two things are this command's own. A `--version` that is not
the project's version is **refused** (`2`) before towncrier runs, because assembling under
another number writes a `CHANGELOG.md` heading that `release check` then refuses — set the
version in every source first, then assemble under it. And a towncrier that cannot be run is a
finding (`1`) that names it as the development dependency it is, rather than a traceback.

Without `--draft` the fragment files are consumed, which is a write to the repository; with it
nothing is written and the rendered section is printed.

## `keelline release hashes [--check]`

Record the sha256 of every file the harness executes without Python, into `hooks/hashes.json`
beside them.

```bash
keelline release hashes            # write the record
keelline release hashes --check    # report drift, write nothing
```

Three files are recorded — `hooks/run-hook.sh`, `hooks/hooks.json` and `scripts/keelline` —
because those are the ones a harness runs directly; a wheel's own contents are the packaging
tool's to attest. The record is refused rather than written when any of the three is missing: a
record naming two of three reads as a clean comparison for the third.

**Not a release-time command.** `keelline release check` compares the record to the tree on
every run, so editing any of the three without re-recording fails the gate in the same commit
rather than at a tag — which is what makes it a record somebody has watched fail. `doctor
files` reads the installed record against the installed files, and reports post-install
modification, a partial update or a broken checkout. An attacker who edits both the files and
the record is not this check's threat; tag protection and the pinned SHA are.

**Writes** `hooks/hashes.json`, and nothing under `--check`. Exits `0`, `1` on drift. Under
`--check --json` the object carries `summary`, `files` and `problems`, in both outcomes, for
the reason `release check` above gives.

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
is silent rather than closed. The wrapper cannot defend its own mode, so `keelline doctor` is
what catches it: the `files` row goes **red** on a cleared bit and hands you the `chmod +x`. Run
it after anything that rewrites the plugin directory.

**What a session hears about the overlay it is bound to: `overlay-status`.** The `attach` area
registers one `SessionStart` handler — `open`, with a `once_key`, so it speaks **at most** once
per session: the marker is banked only when the handler had something to say, so a session that
hears a line hears it once, and a repository with nothing to report is asked again on every
`startup`, `resume`, `clear`, `compact` and `fork` the matcher above covers — and it says
nothing at all unless `[memory] mode` is `overlay`. Ten fixed lines, each carrying at most a
count, joined by newlines in this order: **no overlay recorded** on this machine, or one that
**could not be asked** about, which is a machine configuration file that will not parse; this
repository **not attached** to that overlay, or the overlay recording **a different remote**
under this project's name; **a memory path refused**, so the notes were not examined at all; how
many note groups are **real directories** rather than links into the overlay; the overlay's
`keelline.requires` in **a form this Keelline cannot read**, or naming **a floor this Keelline
does not meet**; and — only when none of those fired — the overlay's branch having **no
upstream**, and the counts of its **unpushed commits and uncommitted changes**. A bound, linked,
up-to-date repository on a satisfied Keelline hears nothing. Not one byte a repository wrote
reaches any of those lines: `project.name`, `memory.groups`, `paths.memory` and both remotes are
read and none is quoted back, because the field these lines land in is `additionalContext` —
model input with no delimiter and no trust record.

**What it costs, and on which repository.** The binding's own `origin` query runs on every
invocation, at git's five-second cap. The last two lines cost two more `git` calls at two seconds
each, and they are reached **only when nothing above them found anything wrong** — a finding
short-circuits them. So the repository that pays all three, nine seconds against the entry's own
ten-second budget shared with `worktree-link`, is the bound, linked, up-to-date one that then
hears nothing; and because the `once_key` marker is banked only on a line actually delivered,
that is also the repository asked again on every event the matcher covers. A repository with a
finding pays five seconds, hears its line, and is not asked again.

Which is why those last two `git` calls are gated on the event's own `source`: on a **compact** —
the running conversation continuing, under the session id the marker is filed under — they are
skipped, so a healthy repository costs five seconds there and not nine. `startup`, `resume`,
`fork`, `clear` and a payload carrying no `source` all pay: a resume is a new launch, often days
later, over an overlay the conversation may have left dirty, and an invocation Keelline cannot
place in a context is treated as a new one rather than as one already answered. The cost is that
an overlay which becomes unpushed *during* a session that started clean is not reported at that
session's compactions, only at its next resume or startup; `keelline doctor` answers on demand. And the overlay is never a plugin Keelline
executes anything from — its
`hooks/hooks.json` stays empty; hook entries the owner keeps in *common/claude/hooks.json* and
`projects/<name>/claude/hooks.json` reach a session only through `attach`'s explicit, ledgered
merge.

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
hook is `keelline setup --git-hooks`, and removing it — restoring whatever it chained to — is
`keelline setup --git-hooks --uninstall`; both are documented below.
`keelline.guards.api.install` is the same call for a caller embedding Keelline.
**Writes** `FILE`.

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

## `keelline test attribute --command CMD [--base REF]`

Run one failing command three times and say what the three exit codes mean. The three trees:

1. **The working tree as it is** — the command runs with `--root` as its directory, exactly
   where you are.
2. **`HEAD`'s committed tree** — extracted with `git archive` into a scratch directory.
3. **The merge-base with the base branch** — extracted the same way. The merge-base, not the
   base's tip: a base branch that advanced after the fork would otherwise carry commits that
   are not "before this change" into the before side.

`--base` defaults to `origin/<[project] base_branch>`; pass it to compare against another ref.

**This command writes nothing**, and nothing in it runs `git checkout`, `git stash` or `git
reset`: the two committed trees are extracted into a temporary directory that is removed before
the command returns, and your checkout is never moved between commits or restored from one.

**Your command is another matter, and the distinction is the whole safety property.** Run 1
executes it *in the working tree*, so whatever it writes there, it writes — the example above
leaves a lockfile, a virtual environment, `.pytest_cache` and `__pycache__` behind exactly as
running it by hand would. What this command guarantees is that it does not move your checkout
to another commit to get its "before" reading, not that the three runs leave no trace.

**The command is yours, and so is its environment.** `--command` takes the exact failing
command *including the sync it needs to be meaningful* — `uv sync --locked && uv run pytest
tests/x.py::t` for a Python project, the equivalent for another stack. That sync is the whole of
what makes runs 2 and 3 comparable; a command that does not sync compares two drifted
environments and the verdict is worth nothing. It is also what makes this command the same tool
for every language.

The verdict, from runs 2 and 3 first and run 1 only when both passed:

| `HEAD` | merge-base | working tree | Verdict |
|---|---|---|---|
| fails | fails | — | `pre-existing: the failure is on the merge-base too, so it is not this change` |
| fails | passes | — | `this change: HEAD fails and the merge-base passes` |
| passes | fails | — | `this change fixed a pre-existing failure: HEAD passes and the merge-base fails` |
| passes | passes | fails | `environmental: HEAD passes when synced and fails in the working tree as it is` |
| passes | passes | passes | `not reproduced: all three runs passed` |

Five sentences, and the four `HEAD`/merge-base cases are exhaustive: there is no sixth verdict
and no fall-through. A run that **did not execute** — the launcher's wall-clock cap, or a
command it could not start at all — is a failure naming which of the three it was, never a
verdict. That matters more than it sounds: a cold sync in a fresh extraction is the likeliest
thing to hit the cap, and two timed-out runs scored as exit codes would read as "fails on
both", which is the one wrong answer a tool feeding a ledger entry must not give. Narrow the
command to the failing test rather than asking for a wider cap.

`--json` carries `summary` (the line the command would have printed), `runs` (`head_ambient`,
`head_clean`, `base_clean` — the three exit codes in the order they were run), `base` (the ref
asked for), `merge_base` (the commit actually extracted) and `verdict`. Record the last four
where the failure is discussed: a verdict without its inputs cannot be re-run.

Exits `0` with a verdict, `1` when the merge-base cannot be resolved (`is origin/main
fetched?`), when `git archive` fails, or when an archive is missing tracked files because the
archived tree's own `.gitattributes` excluded them, and `2` when `--base` is shaped like an
option, which is refused above the first subprocess rather than handed to `git` as one.

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
`REF...HEAD` touches, `REF` defaulting to `origin/<project.base_branch>`. Five rules, each from a
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

## `keelline init --yes [--dry-run] [--no-ci] [--root PATH] [--machine PATH]`

Writes a repository's Keelline footprint, once. It is the only command that creates the
documents every other command reads, and the only one that writes `keelline.toml`.

**`--yes` is required, and it means "take the detected defaults".** The questions §8.1
describes — the project's name, its base branch, its preset — ship with the onboarding lane;
until then the command detects what it can, and an invocation without `--yes` is refused (`2`)
saying so. What it detects: the project's name from `origin`'s last path segment, `.git`
stripped and lower-cased, else the checkout's directory name; the base branch from
`refs/remotes/origin/HEAD` with `origin/` stripped, else `main`; the agent surfaces from which
of `.claude/` and `.codex/` the repository carries, both when it carries neither; and
`[keelline] profile` from the first shipped profile whose markers sit at the root (`python`:
`pyproject.toml`, `setup.py`, `setup.cfg`, a requirements file, a `Pipfile` or a lockfile),
written only when one is found. Both name candidates, the remote's segment and the directory
name, are repository-authored, so one outside `[project] name`'s grammar is refused naming the
grammar and the remedy and never the value.

**A `keelline.toml` you wrote is the answer sheet, not an obstacle.** Every key it carries is
read and kept — the name, the paths, the memory mode, the budgets — and the file itself is not
replaced: it is a create-once artifact, so a repository that already has one is reported
`skip_modified` ("create-once, and the file is already there") and the document comes back byte
for byte. The paths it declares are where the footprint lands. A repository with no
`keelline.toml` gets one written from the detected values, headed by a comment naming the four
keys that are Keelline's to rewrite: `[keelline] version`, `state` and `enforced`, and
`[ci] ref`. A file that is not valid TOML is a failure (`1`) naming the file. A repository that
already carries `.keelline/manifest.json` is refused (`2`): re-running `init` is
`keelline upgrade`.

**Two passes, both planned before either is applied.** The three write-once files are one pass
and the rest of the footprint is the other, because two artifacts cannot target one file in one
pass and both the `AGENTS.md` skeleton and its `harness` region land on `AGENTS.md`. A refusal
in either plan stops the run with nothing written and no manifest, and `--dry-run` is that same
branch rather than a second code path — it reports both plans and writes nothing. On a
repository with no `AGENTS.md` the dry run plans the region as a *create* of a region-only file
and the real run re-plans it as a *region_update* into the skeleton the first pass has just
written; the report carries one fixed sentence saying the bytes inside the markers are the same
either way.

| id | pass | kind | target | what it holds |
|---|---|---|---|---|
| `config` | write-once | once | `keelline.toml` | the document this run rendered |
| `agents-skeleton` | write-once | once | `[paths] agents_md` | a skeleton headed with the project's name, stating this project's own budgets |
| `claude-md` | write-once | once | `CLAUDE.md` | a one-line pointer at `[paths] agents_md`, whatever that file is called |
| `documentation-policy` | footprint | template | `<architecture>/documentation.md` | where each kind of fact belongs |
| `adr-template` | footprint | template | `<adr>/0000-template.md` | the four-heading decision record |
| `ledger-runbook` | footprint | template | `<runbooks>/bug-reports.md` | how to file, close and reference an entry |
| `ledger-audits` | footprint | template | `<bugs>/audits/README.md` | what an audit record is |
| `bug-index` | footprint | template | `[paths] bug_index` | the generated index, rendered empty |
| `roadmap` | footprint | template | `[paths] roadmap` | `Now`, `Next`, and the trail block |
| `roadmap-history` | footprint | template | `[paths] roadmap_history` | an empty history |
| `trail` | footprint | template | `trail.toml` beside the roadmap | one theme, no declared states |
| `specs-keep`, `plans-keep` | footprint | template | `<specs>/.gitkeep`, `<plans>/.gitkeep` | nothing, so the trail lists no documents |
| `gitignore` | footprint | managed region | `.gitignore` | the same block `attach` writes |
| `agents-md` | footprint | managed region | `[paths] agents_md` | which paths this repository's Keelline uses |
| `ci-workflow` | footprint | template | `.github/workflows/keelline.yml` | the pinned call to the reusable gate |
| `profile-rules` | footprint | template | `<keelline>/rules/<profile>.md` | the profile's rules, the one copy a project edits; only with `[keelline] profile` set |
| `claude-rules` | footprint | template | `.claude/rules/keelline-<profile>.md` | a `paths:`-scoped pointer at `profile-rules` for Claude Code; only when `[keelline] agents` lists `claude` |

With a profile set, the `agents-md` region also names the profile's rules file and lists the
lines under its *Before the first command* heading, so every harness that reads `AGENTS.md` has
them before its first command. A name in `[keelline] agents` that no harness answers to is
counted in a `note:` line and never printed.

**The workflow pins what `[ci] ref` says, and nothing else.** The rendered file calls
[the reusable workflow](#the-reusable-workflow) at the ref `keelline.toml` carries *after this
run*, and those two are one value by construction — which is the invariant `keelline doctor`'s
`ci-ref` row enforces from the other side ("the workflow pins a different ref from `[ci] ref`,
so the gate that runs is not the one recorded"). On a repository this run creates the document
for, the ref is the commit of the Keelline release running, asked of the public repository's own
`v*` tags and written into `[ci] ref` beside the workflow. On a repository that already had a
`keelline.toml`, that document is not rewritten — so the workflow pins the ref **it** records,
and `doctor` judges whether that is a released commit, which is its job.

Seven states cost the artifact rather than the run, each reported under `skipped` with one
sentence: `[ci] mode` is `none`; `[ci] mode` is `uvx`, whose form of the gate ships with a later
lane; the public repository could not be asked for its tags; no released tag matches the
Keelline running, which is every repository's state before the first release; the `keelline.toml`
this repository already had records no `[ci] ref`, so there is nothing a workflow could pin that
anything records; `[ci] ref` is not a full-length commit sha, which is the only immutable form
and the only one `init` renders — the documented mutable `v1` alias is a file you write by hand;
and `[ci] gate_branch` is not a plain branch name. `--no-ci` is the first of those on purpose: it
puts `[ci] mode = "none"` into the document this run builds and asks no remote anything. **On a
repository that already has a `keelline.toml` the flag governs this run and nothing more** — that
document is a create-once artifact, reported `skip_modified`, so the file still says whatever it
said and the next `init` would ask the remote again. Writing `none` there is yours to do.

**The two states about the remote are reported only on a run that creates the document.** On the
adoption path the answer is the fifth one whatever the remote said, because it is the whole
reason: a pin this run resolved would be written into a create-once file that is already there,
so nothing would record it. Reporting "run `keelline init --yes` again with the network
reachable" there would send you back to a command that cannot help — by the time you read it,
`.keelline/manifest.json` exists and `init` refuses to run again at all. `keelline upgrade` is
the command that can: `[ci] ref` is one of Keelline's keys in any `keelline.toml`, so it records
a released commit there in place and renders the workflow around it. On a run that created the
document, the unreachable remote's sentence names both remedies: `keelline init --yes` with the
network reachable while nothing is written yet, and `keelline upgrade` once it is.

**Reads** `keelline.toml` when there is one, `.keelline/manifest.json`, `git` for the name and
the base branch and for the public repository's tags, which harness directories the root carries
(`.claude/`, `.codex/`), each shipped profile's marker files at the root, every file an artifact
targets, and `git check-ignore` for each existing file a write targets at a place a `[paths]`
value chose. **Writes** `keelline.toml`,
`CLAUDE.md`, `[paths] agents_md`, `.gitignore`, the documents in the table above (the profile's
rules and the Claude pointer only when a profile is set), `.github/workflows/keelline.yml` where a
ref is recorded, `.keelline/manifest.json`, and `.keelline/local/artifacts.json` when
`[artifacts] local` lists anything —
every one of them through the scaffold engine, so every target goes through the containment walk
and none may leave the project root or pass through a symlink.

Exits `0` on success. `1` on a finding: either plan carries refusals — the report's REFUSED section
names each, nothing was written and no manifest exists — or a `keelline.toml` that is not valid
TOML, or the merged document the loader itself refuses (an unknown section or key, a `[project]
name` outside its grammar, a value of the wrong type, a machine configuration file that does not
load). `2` on a refusal above the plans: no `--yes`, a repository already initialised, a detected
name outside the grammar, a `[paths]` value outside the plain-path grammar, naming git's control
directory or Keelline's own `.keelline/`, or reaching through a component that is a symlink — all
three refused by the loader before a plan exists — two artifacts of one pass that resolve to one
file, which is named with the two `[paths]` keys to separate, two artifacts of either pass that
resolve to one file (`roadmap = "CLAUDE.md"`, say), named the same way, since only the `AGENTS.md`
skeleton and its region share a file by design, an `[artifacts] local` list naming a profile
artifact, which every pointer at it reads at its committed path, one naming `config` or `gitignore`,
which only work at the repository root, and a write git would hide, at an existing file a `[paths]`
value chose, which the refusal names, or one git cannot answer for inside a repository because it
timed out or is not installed (see `upgrade`'s boundary).

`--json` carries `dry_run`, `adopted`, `once` and `footprint` (each the plan's own rendered
report), `writes` (both plans' targets), `skipped`, `pin` (the release this run resolved,
`{tag, sha}` or `null`), `asked`, `note`, `ref` — what `[ci] ref` says on disk after the run
and so what the workflow pins, empty when no workflow was planned — and `unknown_harnesses`, how
many names in `[keelline] agents` no harness answers to.

---

## `keelline upgrade [--dry-run] [--force PATH]… [--root PATH] [--machine PATH]`

Refreshes a repository's footprint after a Keelline update, keeping every hand edit. It moves
`[keelline] version` to the Keelline running, re-plans every footprint artifact against
`.keelline/manifest.json` by hash, and never re-plans the write-once files: `keelline.toml`,
`CLAUDE.md` and the `AGENTS.md` skeleton are yours after `init`.

`--dry-run` reports everything and writes nothing. `--force PATH` overwrites or removes one file the
report named `skip_modified`, as a path relative to `--root` exactly as the report prints it; repeat
it for each file. It reaches a file you edited, one Keelline never wrote, and a changed or
unrecorded copy under `.keelline/local/artifacts/`, but not a file left at an artifact's old place
(`relocated and hand-edited`, or a recorded target the artifact cannot produce): that one is yours
from then on, to keep or delete by hand. A leading `./` is dropped, and an absolute path or one with
a `..` component is refused (`2`) naming the rule. A forced path no planned action names — a typo, a
case difference, or a file with nothing to force — is counted in a `note:` line and forces nothing.

**Four verdicts.** A file whose bytes are still the ones the manifest records is refreshed
(`update`, or `region_update` for a managed region) when this Keelline renders it differently,
and reported `unchanged` when it does not. One that is missing is created. One you edited is
`skip_modified` and named, and stays as it is until `--force` names it. So is a file Keelline
never wrote at a path it would write (`exists and Keelline did not write it`); forced, it is
overwritten and recorded, and later runs judge it like any file Keelline wrote. An artifact this
configuration no longer produces is removed while its bytes are the ones recorded (`remove`),
and skipped the same way when they are not.

**What is rewritten in `keelline.toml`, and what is not.** Only the values Keelline owns:
`[keelline] version` and, under `[ci] mode = "reusable"`, a `[ci] ref` that is a commit sha or
empty. Every other byte stays where it was — comments, order, blank lines, your keys. A key written
in a shape the editor does not rewrite in place (a dotted key, an inline table, a multi-line value)
is refused (`2`) naming the key and the line to write by hand, before anything is written. When the
manifest's `config` record still describes the file, it is re-stamped with the new bytes; when you
have edited the file, it is not, so `keelline.toml` stays yours.

**Version, `[ci] ref` and the workflow's pin move together or not at all.** Under
`[ci] mode = "reusable"` the workflow pins Keelline by commit, so `[keelline] version`, `[ci] ref`
and the `uses:` line in `.github/workflows/keelline.yml` are one value. When no released commit
of the Keelline running is found — before its tag exists, or with the network unreachable — or
when the workflow would not be rewritten to the new pin, neither key moves: a `note:` line says
`[keelline] version` and `[ci] ref` were left as they are and why, and the rest of the footprint
is still refreshed. A workflow you edited by hand, or one Keelline never wrote, is reported
`skip_modified` and moves with them only under `--force` with the path the report prints for it.
When the report refuses the workflow, or the `CI:` line says none was rendered (a `[ci]
gate_branch` outside the branch-name grammar, say), no flag moves them: the note says to put
that right and run `keelline upgrade` again. The `CI:` line says the workflow pins `[ci] ref` only
when this run created it, refreshed it or found it current; a workflow the report lists
`skip_modified` or refuses was left as it is and may pin anything, and the line says so.

**A `[ci] ref` that is not a commit is yours.** The documented `v1` alias, or any other value
that is not a full-length sha, is a choice to track a moving Keelline, so `upgrade` moves
`[keelline] version` alone: it never replaces that ref with a sha, and never renders a workflow
over the one you wrote around it. The `CI:` line says no workflow was rendered around the ref.

**A project recording a newer Keelline is refused** (`2`), before anything is written: an older
plugin would repin an older release and put older bytes over newer ones. The recorded version is
read by its leading `X.Y.Z` first, so `1.0.0-rc1` is newer than a running `0.9.0`; with the same
`X.Y.Z`, a release is newer than its own pre-release, so a project recording `1.0.0` is refused
by a `1.0.0rc1` build. Update the Keelline plugin, then run `keelline upgrade` with it; never edit
`[keelline] version` to get past it. A recorded version with no leading `X.Y.Z`, such as
`v1.0.0`, is refused too, because which way a move would go is unknown; set it to the release
the project was last upgraded with. So is one sharing the running `X.Y.Z` and differing after it
in a way Keelline does not order — two pre-releases, such as `1.0.0rc1` and `1.0.0rc2`, or a
post-release — and that refusal names the version running: set it to that by hand if it is the
release the project should move to.

**An artifact kept out of git is recorded out of git too.** One listed in `[artifacts] local` lives
under `.keelline/local/artifacts/`, and the committed manifest never records it; instead
`.keelline/local/artifacts.json`, which the ignore block keeps out of git like the artifacts,
records the bytes Keelline last wrote there. A file still holding those bytes is refreshed like any
other when this Keelline renders it differently. One that no longer does is `skip_modified`
(`kept out of git, and changed since Keelline wrote it`), because nothing brings it back once it is
overwritten, and `--force` with its path takes it; with that record gone, a file that is not exactly
what this build writes is skipped the same way, saying nothing records what Keelline wrote there.
When an id leaves `[artifacts] local`, or its `[paths]` value moves while it stays there, the
artifact is written at its new place and the copy the record names at the old one is removed while
it holds exactly the bytes recorded for it (`relocated`); otherwise it is `skip_modified`, stays
recorded until it is gone, and `--force` with its path takes it. The record is read as untrusted,
since a clone can commit it anyway: anything but its own exact shape is read as no record at all, it
is never printed, it names nothing outside `.keelline/local/artifacts/`, and it vouches only for a
file there whose bytes are exactly the ones it states.

**Retirement.** An artifact this configuration no longer produces — the profile's rules after
`[keelline] profile` changes, its Claude Code pointer after `agents` drops `claude` — is removed
only at a target this build could have written for it, and only while its bytes are the ones
recorded. The workflow is removed only when `[ci] mode` is `"none"`; a mode this build does not
render, such as `uvx`, is not a request to delete the gate. Every other record in the manifest is
counted in a `note:` line and left where it is, and never named, as is a record saying its
artifact lived inside a file (a region) that this build no longer produces: a region comes out
only through the template that names it, never as a whole file, which is `uninstall`'s rule too.

**The boundary.** Which artifacts exist, and where each could be, are this build's. The `[paths]`
value a target is built from and the digest a record carries are committed. For a whole file, a
commit can make `upgrade` rewrite it only while it holds exactly the bytes the same commit records,
`--force` aside: that overwrites a whole file whatever it holds, one nothing records included, but
only at a path given exactly on the command line, which no commit can supply. A managed region is
inserted into whatever file its key names: a commit that points `[paths] agents_md` at another
tracked file gets the region written into that file, and the diff shows both the edit and the
region. No `[paths]` value may name git's control directory or Keelline's own `.keelline/`, where
attach's ledger and the local-only notes live out of git's sight; the loader refuses either, naming
the key. And a committed `[paths]` value cannot put a write or a removal where git would hide it:
the run is refused (`2`) before anything is written, dry run included, when all three of these hold
for a file it would write or remove — the file exists, git ignores it, and it is at a place a
`[paths]` value chose rather than where the preset puts that artifact. The refusal names each such
file, as the report prints paths, and says to point the key at a path git does not ignore or take it
out. A new file, a fixed name (`CLAUDE.md`, `keelline.toml`, `.gitignore`, the workflow, a harness's
rule) and a preset's own place are never refused, so a `CLAUDE.md` in your global excludes or a
`keelline.toml` in `.git/info/exclude` works as before. A tracked file that matches an ignore
pattern is not ignored, because git shows every change to it; the artifacts `[artifacts] local`
keeps under `.keelline/local/artifacts/` are exempt, since keeping them out of git is what that
setting asks for; and outside a git work tree there is no guard, because there is no diff to hide
from. Inside one (a `.git` in the root or a directory above it), a `git` that cannot answer, because
it timed out or is not installed, refuses the run rather than letting it through. Run it on a
checkout you trust. There are no hooks to re-trust afterwards: `init` writes no project-level hook
entries, so an upgrade changes none.

**Reads** `keelline.toml`, `.keelline/manifest.json`, `.keelline/local/artifacts.json`, every
file an artifact targets, `git check-ignore` for each existing file a write or removal targets at
a place a `[paths]` value chose, and, under `[ci] mode = "reusable"`, the public repository's
tags. **Writes** the footprint through the scaffold engine, and the record of what it wrote kept
out of git, then `keelline.toml`, last, so the version is the commit point: a run interrupted
before it leaves the old version recorded, and the next run re-plans from there.

Exits `0` when it applied the plan or there was nothing to do. `1` on a finding: the plan carries
refusals — the report's REFUSED section names each, and nothing was written — or a `keelline.toml`
that does not load, as for every command. `2` on a refusal before any write: the repository is not
initialised, `keelline.toml` is missing, it records a newer Keelline, a version with no leading
`X.Y.Z` or one Keelline does not order against the running one, a key is written in a shape the
editor refuses, two artifacts resolve to one file (named by artifact and `[paths]` key, as `init`
names it), a profile artifact, `config` or `gitignore` is listed in `[artifacts] local`, git ignores
(or inside a repository cannot say whether it ignores) an existing file the run would write or
remove at a place a `[paths]` value chose, or a `--force` path leaves `--root`. `2` also when a file
cannot be written or removed part-way through; what was already applied stays applied and recorded,
and running the command again re-plans from there.

`--json` carries `dry_run`, `moved` (each `{key, before, after}`; a `before` outside its grammar
prints as `(not a version)` or `(not a commit)`), `held` (the note's sentence, or empty),
`footprint` (the plan's rendered report), `writes`, `skipped`, `orphans` (a count), `pin`
(`{tag, sha}` or `null`) and `asked`.

---

## `keelline uninstall [--dry-run] [--force PATH]… [--root PATH] [--machine PATH]`

Takes back what `init` and `upgrade` wrote. A file whose bytes are still the ones the manifest
records is removed; Keelline's managed regions come out of files that hold other text, and such a
file goes too only when nothing else was in it; the ledger goes last. A file you edited stays
where it is, is reported `skip_modified` with its reason, and is counted in a `left in place`
line. Every recorded artifact is judged, including one this configuration no longer produces, at
a target this build could have written for it, whatever `[ci] mode` says now: the workflow goes
under `uvx` too. Any other record is counted in a `note:` line and left where it is, and never
named, as is a record saying its artifact lived inside a file (a region) that this build no longer
produces: a region comes out only through the template that names it, never as a whole file.

`--dry-run` reports everything and writes nothing. `--force PATH` removes one file the report named
`skip_modified`, as a path relative to `--root` exactly as the report prints it; repeat it for each
file. It reaches what `upgrade`'s `--force` reaches, and likewise not a file left at an artifact's
old place (`relocated and hand-edited`), which is yours to keep or delete by hand. The path rules
are `upgrade`'s: a leading `./` is dropped, an absolute path or one with a `..` component is refused
(`2`), and a forced path no planned action names is counted in a `note:` line and forces nothing.

**Two passes, the footprint first.** The footprint pass removes files and takes the regions out;
a region taken out of a file that keeps other text is reported as
`remove  AGENTS.md  (retired; Keelline's part only, the file stays)`, and a line without that
tail means the file itself goes. Every command that prints a plan says it the same way.
The write-once pass (`keelline.toml`, `CLAUDE.md` and the `AGENTS.md` skeleton) is planned again
after it, so the skeleton is judged once Keelline's region has left `AGENTS.md`: untouched, it is
byte for byte what `init` wrote and goes. A dry run cannot take the region out first, so it
judges the skeleton with the region still in it and calls it edited; a `note:` line says so.
**Forcing `AGENTS.md` takes Keelline's region out of it and never the skeleton**: a forced path
the footprint pass targets never reaches the write-once pass, compared as the engine places each
file, so what you wrote into the skeleton is judged on its own bytes.

**The ignore block goes last, and only over an empty `.keelline/local/`.** The `.gitignore` region
is what keeps `.keelline/local/` out of git: attach's ledger, the local-only memory notes, and the
artifacts `[artifacts] local` keeps out of git. So it is taken out in a pass of its own, after the
disk shows nothing left under `.keelline/local/`. Every directory above a file a pass removed goes
once it is empty, deepest first, and no other: an empty directory a `[paths]` value merely names may
be yours. Then `keelline.toml`, which the write-once pass holds back for this point; then the
ledger: `.keelline/assessment.json`, `.keelline/manifest.json`, and `.keelline/` once it is empty. A
directory someone committed where a ledger file belongs stays. So does a harness's own directory
(`.claude/`, `.codex/`, or the same name in any other case), even when it is empty, whoever made it:
`init` may have created `.claude/` to hold the rule it wrote there, but nothing records who made an
empty directory, and to `init` its presence means the project uses that harness. So a later `init`
detects that harness and lists it in `[keelline] agents` until you remove the directory.

**Refused before any write** (`2`): the repository is not initialised; it is attached to an overlay,
so run `keelline detach` first; `keelline.toml` is missing while the manifest records it, so restore
it; `[artifacts] local` names `config` or `gitignore`, which only work at the repository root, so
take them out of the list; two artifacts resolve to one file, named as `init` names it;
`.keelline/local/` holds files this run would not remove, such as notes, or an artifact kept out of
git that changed since Keelline wrote it, which the refusal counts and never names; git ignores an
existing file the run would remove or rewrite at a place a `[paths]` value chose, which the refusal
names; or a `--force` path leaves `--root`. The count is exact before anything is written, including
what taking a region out of a file kept out of git would leave behind; the record of what Keelline
wrote there, `.keelline/local/artifacts.json`, is Keelline's own and goes once nothing else is left,
before the ignore block. Every artifact it records is judged, a copy left behind when its id left
`[artifacts] local` or its `[paths]` value moved included, so an unedited one goes. Move the files
out; one the report lists `skip_modified` in a file of its own there can be named with `--force`
instead, but an `AGENTS.md` whose region and skeleton are both kept out of git shares one file, and
forcing it takes only the region, so a line you wrote into that skeleton has to be moved. A dry run
reports the count in a `note:` line instead of refusing, even when its plans also carry refusals, so
its report still lists the edited file.

**Refused part-way** (`2`): a file that cannot be written or removed, or files still under
`.keelline/local/` after the write-once pass, which the count before any write should already have
refused; move them out. What was removed stays removed and recorded, and `keelline.toml` and the
manifest are still there, because they go last, unless the last pass removed `keelline.toml` and
then could not write the manifest, which the next paragraph covers; so running the command again
finishes from what the first run left, to the same end as a run that was never stopped.

**Without `keelline.toml`, nothing the manifest records can be judged.** While the manifest still
records the file, the run is refused (`2`) before any write, dry run included: restore
`keelline.toml` (from git, for instance) and run it again. This command drops that record as it
removes the file, so the file was taken by something other than this command, or by a run of it that
removed the file and then did not rewrite the manifest, because it was killed in between or the
manifest could not be written; either way the restored file is judged like any other, and the run
then goes on to the end. When nothing records it — a run stopped between removing it and removing
the manifest, or a `keelline.toml` the project wrote itself before `init`, which `init` never
records — every recorded file stays, a `note:` line gives their count, and only the ledger goes, so
`init` and this command no longer refuse the repository. No other directory is pruned then, because
nothing says where the configuration put its artifacts.

**The boundary.** Which artifacts exist, where each could be and every region's name are this
build's. The `[paths]` value a target is built from and the digest a record carries are committed,
so a commit can make `uninstall` remove a whole file only while it holds exactly the bytes the same
commit records, and a region only where its key names; the diff shows both. No `[paths]` value may
name git's control directory or Keelline's own `.keelline/`, and a symlinked `.keelline/` is
refused. An existing file git ignores at a place a `[paths]` value chose is never removed or
rewritten: the run is refused (`2`) before any removal, dry run included, by `upgrade`'s rule,
naming the files, and so is a run inside a repository whose `git` cannot answer because it timed out
or is not installed. Take Keelline's part out of them by hand, or take the `[paths]` key out of
`keelline.toml`; the run then leaves those files where they are and lists them. That includes a file
Keelline itself created at an ignored place a `[paths]` value chose (`roadmap = "build/roadmap.md"`
under an ignored `build/`, say): creating it was allowed because nothing was there, and by the time
`uninstall` runs it exists, so this refusal meets it, and taking the key out is the remedy that
finishes the run. A `CLAUDE.md` or `AGENTS.md` your own excludes ignore is taken back like any
other. Run it on a checkout you trust.

**Reads** `keelline.toml`, `.keelline/manifest.json`, `.keelline/local/artifacts.json`, every file
an artifact targets, `git check-ignore` for each existing file a removal targets at a place a
`[paths]` value chose, and what is under `.keelline/local/`. **Writes** only removals, and region
removals, through the scaffold engine, and the record of what it wrote kept out of git,
`.keelline/local/artifacts.json`, which each pass rewrites as it removes what that record names;
then removes that record, and the ledger.

Exits `0` when it applied the plans, including when every recorded file was edited and nothing
was removed but the ledger. `1` on a finding: a plan carries refusals — the report's REFUSED
section names each, and nothing was removed — or a `keelline.toml` that does not load. `2` on the
refusals above, before any write or part-way; a repository with no `.keelline/manifest.json` is
one of them.

`--json` carries `dry_run`, `footprint` and `once` (each the plan's rendered report), `left` (the
files left in place, each as the reports print it), `orphans` (a count), `note` (the dry run's
order note, or the missing-configuration count, or empty) and `kept_locally` (how many files
under `.keelline/local/` the run would leave, on a dry run and on a run whose plans refuse; `0` on
a run that removed what it planned).

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

**`--template` needs a template repository of your own.** It names
`<owner>/keelline-overlay-template`, which
[`keelline overlay publish-template`](#keelline-overlay-publish-template---owner-owner---name-name---yes)
publishes to your account at each release. Until you have run that once, `--template` fails
cleanly with `gh`'s own answer, and `--local` renders exactly the same tree here with no
network call — an owner setting up a first overlay can use either.

A template and not a fork: a fork's visibility is bound to the upstream network and cannot be
made private, which is the one outcome this command exists to prevent.

The `--template` path is idempotent, because `gh` can give up on the clone with the repository
already created: a directory that already carries `.claude-plugin/` is left alone and reported.
When `gh repo create` itself fails, the command stops there and reports **its** exit code and
**its** stderr: a `gh` that is not installed, or one that hung, costs one launch rather than
three, and the failure names the binary rather than sending you to `gh auth status` for a
repository that was never there. It also names the precondition above — the template repository
`overlay publish-template` publishes — because that is the usual reason this source cannot
work. When `gh`
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
sixteen files there — both plugin manifests, `hooks/hooks.json`, `.gitignore` and
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

## `keelline overlay publish-template --owner OWNER [--name NAME] [--yes]`

Publishes the repository `overlay create --template` generates from: the shipped
`templates/overlay/` tree, as one commit on `<owner>/keelline-overlay-template`.

```bash
keelline overlay publish-template --owner you          # what it would create, mark and push
keelline overlay publish-template --owner you --yes    # do it
```

Six steps, in this order. It renders the shipped template into a scratch directory; it strips
the scaffold ledger, because a repository generated from a template carries none and publishing
one would make every generated overlay read as hand-edited to `overlay upgrade`; it asks `gh`
what exists under that name; it creates the repository **public** and marks it
`is_template` if it is not one already; it clones it and replaces the tree with the render; and
it commits and pushes to the repository's default branch.

**`--yes` is the gate, and it covers three acts rather than one** — creating the repository,
marking it a template, and pushing. Without it the command renders, asks `gh` what is there,
and reports what it *would* create, mark and push. That is the dry run; there is no separate
`--dry-run` flag, because a second way to say the same thing is a second thing to get wrong.
The gate is a parameter and not a step in a procedure: in a session driven by an agent, a flag
a model can type is not a control, so the flag is where the consent is recorded.

**An existing repository that is not public is refused (`2`), never flipped.** A template is
generated from by other accounts only when it is public, and a repository somebody made private
under that name is not one this command may change a flag on — publish under another `--name`,
or make it public yourself first.

**It runs from your own authenticated checkout by design.** The public repository's CI holds no
credential that can write a second repository, so this is not a workflow and does not become
one: `gh` decides the protocol and carries the token. `gh` that cannot be run at all is a
finding (`1`) naming it.

`--owner` is your account and `--name` the repository (default `keelline-overlay-template`);
both are held to one path segment, and the owner is lower-cased the way `overlay create` folds
it. There is no `--root`: the tree is rendered from this Keelline's own package.

**Writes** nothing outside a temporary directory this command creates and removes. Exits `0`;
`1` on a `gh` or `git` that failed, `2` on a refusal.

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
the overlay's rules this repository already has), the Codex standing-rule files it would
place under `.codex/rules/`, and `real_directories`: how many of this project's memory groups
are still real directories rather than links into the overlay. Read it before the real run:
everything under **Writes** below that carries content from the overlay is named here first.

It exits `1` when that count is non-zero, the same way it does on a mismatch and for the same
reason — both are findings you act on before the real run, and `attach` itself is what
refuses. The count is a count: a group's name comes out of `keelline.toml`, so it is never
printed.

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

**A group that never moved is refused.** `attach` **links**; it never moves a note. So a
`memory.groups` entry that is still a real directory under `paths.memory` would be linked over,
leaving every session reading the repository's own copy while that group's share of the overlay
stayed empty — with the binding record, the settings merge and the ledger already written.
`attach` refuses (`2`) above its first write instead, counts the groups, and names where each
one goes: `<overlay>/projects/<name>/memory/<group>`, and `common/memory` for the shared group.
Moving the notes is yours to do; no command does it for you. The containment that count is taken
under is anchored on the checkout you pointed the command at, not on any path the repository
configures, so a repository cannot move the directory being counted. **And that containment is a
refusal of its own**, distinct from the two above it: a `memory.groups` entry that does not stay
inside this project's `paths.memory` is refused (`2`) rather than counted — `paths.memory` may
itself be a symlink, and then every group leaves the root at once. Its sentence names neither the
group nor the path, both being repository-authored.

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

**The harness memory link is written under a walk that follows no symlink.** The home
directory itself is found and never created — a missing one is a refusal — and every component
below it has to be a real directory: a `~/.claude` linked into a dotfiles tree is refused by
name, above `attach`'s first write, above `detach`'s first withdrawal and above the first note
link a session makes in a worktree, rather than written through. The refusal names the component
and the way out, which is the same one `--settings`
exists for on the `setup` side: make the directory real and have your dotfiles manager adopt the
files inside it.

It also runs `pre-commit install` in the overlay when the overlay carries a pre-commit
configuration and no hook is installed — the machine that cloned an overlay someone else created
never ran `overlay init`. A missing `pre-commit` is a reported note, never a traceback.

Exits `0` on success; `1` under `--check` on a mismatch **or** on a non-zero count of memory
groups that are still real directories, which are the two findings the paragraphs above explain
and the same number for both; `2` on a refusal: a store outside the
recorded overlay, a mismatch without `--trust-remote`, a widening without `--yes`, a checkout
with no `origin` remote, an existing `.keelline/local/attach.json` naming files or settings keys
`attach` could not have written, a `memory.groups` entry that leaves this project's share of the
overlay, a `memory.groups` entry that does not name a subdirectory of this project's
`paths.memory`, or a `paths.memory` that is itself a symlink — a refusal distinct from that one,
and the reason the count above is a count of
groups that stayed inside — a memory group that is still a real directory rather than a link into
it, or a `--machine` outside an interactive shell. Every one of those refusals happens
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

**The `keelline:ignore` region in `.gitignore` goes only if the manifest does not record it.**
On a repository `keelline init` set up, that block is the footprint's — recorded in
`.keelline/manifest.json` as a scaffolded artifact, with the body `attach` writes — and it
stays. Ownership decides, not last writer: the block is committed, so withdrawing it would
take a line out of a tracked file this command never wrote and leave `keelline upgrade`
reading the footprint as hand-edited. A repository with no manifest is one no
`init` has set up, and its region is withdrawn as before.

A manifest this command **cannot read** — unreadable, not a JSON object, or written by a newer
Keelline — is read as no answer rather than as an answer, so the block stays and the detach
finishes. That file is committed and `attach` never opens it, so a clone that ships a broken one
would otherwise attach cleanly and then make every later `detach` exit `2` for ever, with the
only way out being to delete a tracked file out of somebody else's repository. `--json` reports
`ignore_region_removed: false`, and `keelline init` or a hand edit clears the block.

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

## `keelline setup --preset NAME [--yes] [--home PATH] [--settings PATH] [--machine PATH] [--overlay VALUE] [--root PATH]`

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

`--settings PATH` writes the user-scope settings file at `PATH` instead of at
`<home>/.claude/settings.json`, for a dotfiles layout that links that file into another tree.
`stow` folds a package as far as it can, so with `~/.claude` already created by the harness it
links the *file*: `~/.claude/settings.json -> <dotfiles>/claude/settings.json`. No `--home`
value names that target — `--home <dotfiles>/claude` writes
`<dotfiles>/claude/.claude/settings.json`, a file no reader reads — and the refusal that used
to print an unusable remedy now names this flag. The write still never follows a symlink, and a
link *at* the file itself is refused rather than written through — by a check above the first
write, and not by the walk: the root is the directory `PATH` names and the walk is one component
deep, so the walk never opens the final name and the rename underneath it would *replace* a link
rather than refuse it. The refusal names the file the link leads to, which is the path to pass
instead, and a directory at that path is refused in the same place. `--settings` changes nothing
else: the machine configuration file is still `--machine`'s, and the harness memory link is still
under `--home`.

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

Sixteen checks over one installation. It **reports and never repairs**: every finding
carries the command that would fix it, and not one of them is run for you. Nothing is written.

**Several subprocesses are run and every one of them only asks.** Keelline's own
`hooks/run-hook.sh` with `--version`; `git ls-remote --exit-code` against the public
repository's tags, to judge `[ci] ref`, only when one is set; and the `git` queries the other
rows need — where the overlay keeps its hooks, what its `origin` is, and where the note store
resolves to. Four of those are measured on a green attached installation — the wrapper probe and
three `git` questions — and not one of the four leaves this machine. The `ci-ref` row's
`git ls-remote` is a fifth on a repository that records a `[ci] ref` at all, and it is the only
one that does leave: it goes through the `Runner` seam, which is what lets the case that pins the
four answer it in process instead of launching it. That one is bounded at **30 seconds**, and not
at the seam's own five minutes: five minutes is the bound for `gh repo create --clone` and the
clone behind it, and a peer that does not answer must not turn a one-line diagnostic into a
five-minute block. The other `git` questions are `gitenv`'s five seconds and the wrapper probe is
this area's own thirty.

**The rendered workflow is read as a regular file, and to a bound.** That path is the
repository's: a clone chooses what sits at `.github/workflows/keelline.yml`. Anything there that
is not a regular file — a directory, a symlink to a FIFO, a dangling link — is a warning naming
the path and never the ref's own verdict, and so is a file past 256 KiB, the same bound the
`diagnostics` row reads its log under. Not one byte of the file is printed on any arm, and a byte
that is not UTF-8 is replaced rather than raised: it used to reach the report as a red row saying
the check could not run, which is a red a clone could force.

The summary line carries the counts and the names of whichever status most needs reading, capped
the way every summary in this CLI is. The rows are in `--json`, under `checks`, one object per
check with `name`, `status`, `detail` and `remedy`. A remedy that is not in `--json` is a remedy
nobody sees, so that is where they all are.

`status` is one of `ok`, `warn`, `red`, `skip`.

| Check | What it answers | What it reads |
|---|---|---|
| `not-initialised` | whether there is a `keelline.toml` here, and whether it loads | `keelline.toml` |
| `versions` | whether the project's `[keelline] version` is the Keelline running | `keelline.toml`, the package |
| `files` | the hook wrapper's executable bit, and the three shipped files against the hashes the release recorded beside them | `hooks/run-hook.sh`, `hooks/hooks.json`, `scripts/keelline`, `hooks/hashes.json` |
| `wrapper` | whether the wrapper can actually reach Keelline on this machine | one `run-hook.sh open --version`, and only under the plugin root this Keelline is part of |
| `attached` | the overlay binding, and the shape of the harness memory path | `.keelline/local/attach.json`, `~/.claude/projects/<slug>/memory` |
| `hook-entries` | every hook entry, counted by provenance, with any that claims the Keelline marker and is in no ledger named by position | `.claude/settings.json`, `.claude/settings.local.json`, `.codex/hooks.json`, and `~/.claude/settings.json` |
| `codex-trust` | whether any Keelline hook is untrusted on Codex | — |
| `budgets` | every budget that overrides the preset, and every one the ceiling clamps | `keelline.toml`, the preset |
| `bundles` | a bundle that does not fit its slots, and one whose part reaches the cap | the note store |
| `cli-path` | whether `keelline` resolves on `PATH` | `PATH` |
| `pre-commit` | whether the overlay's commit-time secret scan is installed on this machine | the overlay |
| `overlay-requires` | whether the overlay this machine records requires a Keelline the running one satisfies — red when this project keeps its notes in that overlay, a warning when it does not | the overlay's `.claude-plugin/plugin.json`, `keelline.toml` |
| `ci-ref` | whether `[ci] ref` is the commit of a released Keelline tag (or the `v1` alias, reported as mutable), and whether the rendered workflow pins the same ref — under `[ci] mode = "reusable"`, a workflow that is not there at all is a warning and never a green row, and so are a path that is there and is not a regular file and a file past the 256 KiB bound on the read | `git ls-remote --exit-code` over the public repository's tags, bounded at 30 seconds; *.github/workflows/keelline.yml*, read as a regular file and to a bound |
| `store-debris` | files in the note store that are not notes | the note store |
| `diagnostics` | how many reasons the hook sink recorded — a count, never a line of the file | `${CLAUDE_PLUGIN_DATA}/keelline/diagnostics.jsonl` |
| `ignored-env` | `KEELLINE_CONFIG` or `XDG_CONFIG_HOME` set and not honoured | the environment |

**Ten of the sixteen have a `skip` arm — sixteen arms between them: one no build can answer,
and fifteen on a state of this machine or this repository.** A `skip` is **not** a finding and
never reaches the exit code, so read the detail — each one says which measurement it is missing.

The one no build can answer is `codex-trust`: it needs the hash Codex keys hook trust on, which
no spike measured. `ci-ref` was counted beside it and is not any more, and neither is `files`.
`init` writes `[ci] ref`, so what `ci-ref`'s skip reports is a state — this repository records
none — and which state is the ordinary one moves with the release history rather than with any
code here: while no released tag matches the Keelline running there is no commit to pin, so
`init` records nothing and the row skips on a correct installation; once a release exists, a
repository `init` set up carries a ref and the row answers. `files` compares the installed
plugin against the hashes the release recorded beside it, and skips only on a build carrying no
such record.

The nine that skip on a state are `files` and `wrapper`, when there is no plugin root this
process can vouch for; `attached`, when this machine records no overlay to check the ledger
against, or the overlay could not be asked at all; `pre-commit` and `overlay-requires`, when
no overlay root is recorded on this machine **or** when the root it records is not a directory
— two different arms with two different sentences, because a machine that recorded an overlay
and then moved it is not a machine that recorded none; `overlay-requires` again when the
overlay declares no Keelline requirement; `bundles` and `store-debris`, when the note store does
not resolve; `diagnostics`, when no harness data root is set in the environment; and `ci-ref`,
when no `[ci] ref` is recorded. `files` has a second state arm of its own — a plugin built
before the release record existed carries none, and it says so rather than comparing anything.

**A `skip` does not mean there is nothing to do.** Seven of the sixteen arms carry a remedy:
the two plugin-root skips, `wrapper`'s named-root skip, both of `attached`'s, and the
moved-overlay arm of `pre-commit` and of `overlay-requires`. The dividing line is not "always"
versus "on a state" — every other arm skips on a state and carries nothing: `bundles`,
`store-debris`, `diagnostics` and `ci-ref`, the *no overlay recorded* arms of the two overlay
rows, `overlay-requires`' no-requirement arm, and `files` on a build with no release record. It
is whether the skip is itself worth acting on. Those seven report something wrong that no other
row will tell you: a plugin root nothing can find, a root that will be read and never executed,
a recorded attach the overlay could not confirm, an overlay root recorded and not there. The
other nine report a measurement that is simply unavailable — no store, no overlay, no overlay
requirement, no harness data root, no `[ci] ref`, no release record in this build, no way to ask
Codex — and no command in that row's gift changes it.

**The one to read first is the plugin root**, because it is the quietest and the worst. When
this process can find no plugin root at all, `files` and `wrapper` both skip — two rows, no red,
and every hook entry on this machine silent. Both carry a remedy: run `keelline doctor` from the
plugin's own Keelline so its root answers for itself, or set `CLAUDE_PLUGIN_ROOT` to where the
plugin is installed, which lets `files` read the wrapper even though `wrapper` still will not
run it.

One more case is not a skip but produces fifteen of them: with no `keelline.toml` in `--root`,
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

## The reusable workflow

`.github/workflows/check.yml` is a `workflow_call` workflow a project runs its Keelline gates
through. `keelline init` writes the caller —
[`.github/workflows/keelline.yml`](#keelline-init---yes---dry-run---no-ci---root-path---machine-path)
— so most projects never type these lines; what follows is what that file contains, and what to
write by hand if you would rather. Three lines in the caller:

```yaml
jobs:
  keelline:
    uses: Nezhinskiy/keelline/.github/workflows/check.yml@<40-hex sha>
    with:
      base: main
```

| Input | Default | Meaning |
|---|---|---|
| `base` | `""` | the branch the gate's configuration is read from; empty means the pull request's base, and on a push the repository's default branch |
| `path` | `"."` | the project root inside the caller's checkout, for a monorepo or a fixture. A **plain relative path** — letters, digits, `.`, `_`, `-` and `/`, with no `..` component — and anything else is refused before a gate runs, because the value reaches the run's own outputs and those carry whether the gates enforce |
| `python-version` | `"3.13"` | the interpreter Keelline runs on; 3.11 is the floor |

The caller's job needs `contents: read`. That is the default, so the three lines above are
enough — but a caller that sets `permissions:` at workflow level replaces the default rather
than adding to it, and a called workflow cannot grant itself a scope the caller did not have.
`permissions: {}` at the top of the calling file therefore fails this workflow at its first
checkout, with an error that names neither the cause nor the remedy. Give the calling job
`permissions: { contents: read }` if the file sets any permissions at all.

It checks out the caller, checks out Keelline **at the commit the `uses:` line pins** — read
off the platform's own record of which reusable workflow is running, never off the caller's
inputs, and asserted against `git rev-parse HEAD` before anything else runs — and runs
`docs check`, `bugs check`, `plan check`, `commit check` and `docs trail --check` with
`python3 -m keelline`. No resolver and no build backend; the network is the two checkouts and
whatever `setup-python` fetches when the runner has no matching interpreter cached.

**Where the configuration comes from, and why it is not the tree under review.** The state the
gate enforces on is read from `keelline.toml` **on the base ref**, and on any branch but the
base branch itself the tree's copy must equal it byte for byte — once the base's state is
`installed`, or the run fails before a gate runs. While the base is still `initialised` or
`adopting` the difference is one `::warning` annotation and the run goes on, which is the
same advisory rule the next paragraph states for the gates themselves. A pull request that
could turn its own gates off is not a gate; which keys a pull request may eventually change is
a question the `assess` lane answers, and until it ships the answer is none. The base ref
itself is the pull request's base as the platform reports it, the caller's `base:` on every
other event, or the repository's default branch — none of the three readable out of the tree
under review, and on a pull request a `base:` that disagrees with the platform's answer is
refused rather than preferred. The call site is the remaining surface: `.github/` is under
CODEOWNERS here, and a project adopting this workflow wants the same plus a required review
and a required status check, because the `uses:` line and its `with:` block live in a file a
pull request can edit.

**Advisory until the base says `installed`.** While the base's state is `initialised` or
`adopting`, or while the base carries no `keelline.toml` at all — the bootstrap, which is every
project's first pull request — every gate still runs and every failure is one warning
annotation, and the job is green (D8). Once the base's state is `installed`, a failed gate
fails the job. Every gate runs whatever the one before it said, so a project fixing its
documents does not pay a round trip per finding.

**Pin it by SHA.** A reusable workflow's ref is resolved when the run is created, so `@v1`
and `@dev` are a moving Keelline running against your repository (D16). `keelline init` writes
that pin, and writes it from `[ci] ref` in `keelline.toml` so that the file and the
configuration cannot come apart: on a repository it initialises from scratch that value is the
commit of the released Keelline running, read off the public repository's own `v*` tags rather
than off anything the project says; on one that already had a `keelline.toml`, it is the ref
that file records.
`keelline upgrade` moves it, with `[keelline] version`, and the file says so in its own first
lines. **A project with no release to pin gets no workflow at all**: before the first Keelline
tag there is no commit to name, so `init` reports the workflow skipped with the reason and writes
nothing into `.github/`, and `keelline upgrade` renders it once a release matches. `@v1` is the
documented opt-in for a project that would rather track the major, written by hand;
`keelline upgrade` then moves `[keelline] version` alone and leaves the ref and that file as they
are.
`smoke-release.yml` in this repository runs both moving forms on demand, so that they are known
to work — it is not a form this reference tells you to write.

**What proves it.** `.github/workflows/smoke.yml` installs this plugin from the checkout with
the real harness CLI under a temporary configuration directory, feeds every `hooks/hooks.json`
entry the event it is filed under through the *installed* wrapper, runs `doctor` over the
result, runs the clone-to-exfiltration scenario — a hostile clone attempting to reach the
model through committed memory — and calls this workflow against
the committed fixture project — so the reference above is checked by a run and not only by
this page.

**Checked out with `fetch-depth: 0`.** `plan check` reads a merge base and `commit check` reads
a range; a shallow checkout has neither, and the run says so rather than passing over a history
it cannot see. `persist-credentials: false` on both checkouts, so nothing a gate reads can
reach a token.

---

## Shared flags

Six flags mean the same thing wherever they appear, and each has exactly one sentence. Both
tables below are held to `keelline.command`'s own constants, row by row, by
`tests/test_documents.py` — so a sentence cannot be spelled by hand here any more than it can be
in a parser, which is the whole point of the rule.

| Flag | What it means |
|---|---|
| `--root` | project root (default: current directory) |
| `--machine` | machine configuration file to read |
| `--store` | resolve the memory store at this path |
| `--dry-run` | report what would change and write nothing |
| `--home` | the home directory to read and write under (default: the real one) |
| `--check` | report drift instead of writing, and fail if there is any |

`--check` is the CI half of `--dry-run`: both read and write nothing, and `--check` fails when
anything differs. `keelline bugs index`, `keelline docs trail`, `keelline memory index` and
`keelline release hashes` all take it with that meaning.

Five commands mean something else by a shared name. Each is a **named exception** — a decision
that the flag means something else, not a sentence that drifted — and each has its own constant
beside the six above:

| Command and flag | What it means there |
|---|---|
| `keelline overlay create --root` | directory to create it in (default: current directory) |
| `keelline overlay init --root`, `keelline overlay upgrade --root` | the overlay root (default: current directory) |
| `keelline setup --root` | the repository --git-hooks installs into, and the project root --overlay must not be recorded inside of (default: .) |
| `keelline setup --machine` | the machine configuration file to write (default: ~/.config/keelline/config.toml, the file every reader reads) |
| `keelline attach --check` | report the binding, the diff and the groups that never moved, and write nothing |

`attach --check` reports the way the other four do and exits differently on purpose: its `1` is
a binding **mismatch**, not a non-empty diff. A diff carrying allow rules is the ordinary state
of a first attach and is exactly what the `--yes` gate exists for — the refusal `attach` raises
names this flag as the way to read that diff first. A `--check` that failed whenever the run
would widen would make the documented remedy itself a failure.

---

## Configuration

`keelline.toml` in the project root, committed. Every value is repository-controlled, which is
why so few of them are trusted with anything.

```toml
[keelline]
version = "0.1.0"        # required; there is no default
state = "installed"      # initialised | adopting | installed — default: initialised
enforced = []            # tool-owned: the gates promoted while adopting
preset = "recommended"
profile = ""
agents = ["claude", "codex"]

[project]
name = "widget"          # one lowercase path segment
base_branch = "main"
release_branch = "main"

[paths]                  # each must stay inside the root, and out of .git and .keelline
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
keelline = "docs/keelline" # Keelline's own project files: <keelline>/rules/<profile>.md

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

[artifacts]
local = []               # scaffold template ids whose artifact is written under
                         # .keelline/local/artifacts/ instead of being committed; never
                         # config or gitignore, which only work at the repository root

[ci]
mode = "reusable"        # reusable | uvx | none — how this project means to be gated
ref = ""                 # the commit of the Keelline release the workflow is pinned to;
                         # `init` writes it; `v1` is the documented mutable opt-in
gate_branch = "main"     # the branch a gate reads its configuration from

[gates]
builtin = ["docs", "bugs", "plan", "commit", "trail"]  # validated now; honoured later
custom_timeout_seconds = 600  # how long one of your own gates may run
# [gates.custom.tests]         # zero or more gates of your own, each a table like this
# run = ["pytest", "-q"]       # an argv, never a shell string

[commit_messages]
attribution_check = true # whether `commit check` enforces the attribution block
types = ["feat", "fix", "docs", "test", "refactor", "style", "chore", "harden", "guard"]
```

**Ten sections, and the list is closed**: a section this block does not show is refused when
the file loads (`unknown section(s)`), so the grammar above is the whole of it. All three
`[ci]` keys are read today: `mode` decides whether `keelline init` renders a CI workflow at all
and which form, `gate_branch` is the branch the rendered workflow watches on a push and the
default it passes as `base:`, and `ref` is written by `init` and judged by `doctor`'s `ci-ref`
row. `[commit_messages] attribution_check` is read by `commit check` and `[artifacts] local` by
the scaffold engine. `[commit_messages] types`, `[keelline] enforced` and all of `[gates]` are
read by nothing yet but the loader, which validates them; they are accepted so that a project
can record its intent without the loader refusing the file, and the lane that reads each will
say so.

Every value above is what a key you leave out takes, from the `recommended` preset — with two
exceptions, and one line that is an example rather than a default. `[keelline] version` and
`[project] name` have no default at all and are yours to write: a file without `version` does
not load at all (`[keelline] is missing required key(s): version`). And `[keelline] state`
defaults to `initialised` — it is one of `initialised`, `adopting` and `installed`, and the
`installed` above shows a set value, not what an omitted key takes. Everything from
`[project] base_branch` down is the preset's default exactly as written.

**Gates.** A gate is one check run over a pull request. `[gates] builtin` names which of
Keelline's own five the project means to run, all of them by default, and each
`[gates.custom.<name>]` names one of the project's own: `run` is an argv to run from the
project root, never through a shell, given `custom_timeout_seconds` to finish, and a non-zero
exit is its one finding. A custom gate's name is one lowercase path segment, neither a built-in
gate's name nor `config`, which names the configuration check. **The keys are accepted and
validated when the file loads; the gate that honours them ships later.** Until it does,
[the reusable workflow](#the-reusable-workflow) runs every built-in check whatever
`[gates] builtin` says, and nothing runs a custom gate. When one does, it will run only from a
command a person or a workflow runs on purpose, never from a hook or `doctor`, so running such a
command in a clone runs the commands that clone configured, as running its test suite would.

**Enforcement per gate ships with that gate.** `[keelline] enforced` is meant to list the gates
promoted while a project adopts Keelline, and `state = "installed"` means every gate the project
runs. Both keys are Keelline's to write (`keelline adopt begin` and `keelline adopt promote`,
which ship later), and the loader already holds them together: an `initialised` project lists
none, and an `installed` one lists every gate or none. Nothing reads the list yet. Until the
gate ships, the reusable workflow enforces by `state` alone: once the base's state is
`installed` a failed check fails the job, and before that every failure is a warning.

**Which command reads which path.** `agents_md` and `roadmap` are the two documents `docs check`
budgets, and the roadmap is also what `docs trail` writes into; `specs` and `plans` are the two
trees `docs trail` lists, and `plans` is where `plan check` looks for the plans a diff touched.
`bugs` is the ledger's entry directory and `bug_index` its generated index — `bugs new`,
`bugs index`, `bugs check` and `bugs renumber` all read both — and `runbooks` supplies the
`<runbooks>/bug-reports.md` link that index's generated header writes. `memory` is the note
store, which `memory refs` walks. `keelline` is the directory Keelline's own project files go
under, so that `uninstall` can account for them and a reader can find them; a stack profile's
rules are the first, at `<keelline>/rules/<profile>.md`. The remaining three are read for their
location alone, and so is every one of the others: `bugs check` treats the first component of
every `[paths]` value that has more than one — `docs`, for the defaults — as a directory
documents live in, and therefore as a place a citation of an entry file may be written and must
resolve. Pointing a path key somewhere unusual widens that sweep; it cannot take a document
outside it, because a value that leaves the root is refused before any command runs.

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
preset = "recommended"   # the preset `setup` applies

[overlay]
root = "~/keelline-overlay"   # only read in overlay mode
```

`keelline setup` writes a third table, `[machine]`, into the same file — `version`, the
Keelline that ran, and `installed`, the date it ran. It is `setup`'s record of what it did, not
a setting: it is written, never hand-edited, and a file that has never had one loads fine.

**This file's location is not selectable by a repository.** The path is
`~/.config/keelline/config.toml`, and neither `KEELLINE_CONFIG` nor `XDG_CONFIG_HOME` changes
it: a committed `.claude/settings.json` `env` block would otherwise choose your overlay root
and your trust record. Pass `--machine <path>` to read a different file — a path you typed
rather than one an environment chose, and honoured by every reader of it.

Only `[overlay]` and the trust record used to be held to that rule while `[personal]` followed
the environment, so one command could read the two halves of this file out of two different
files: `[personal]` honoured, and the overlay silently unrecorded a few lines below it.
