# Changelog

<!-- towncrier release notes start -->

## 0.2.0 (2026-09-30)

### Fixed

- A first `stayfixed attach` now writes the store's `MEMORY.md` when there is none. The index link
  it creates used to dangle, and `stayfixed memory index --check` reported the index out of date,
  until `stayfixed memory index` was run.
- A freshly created overlay now passes `claude plugin validate`: its marketplace names an `owner`
  and both plugin manifests an `author`, which `stayfixed overlay init` sets to your account (an
  existing name of your own is kept). The documentation the overlay ships in `common/memory/` is
  now `_README.md`, which the note reader skips. `stayfixed overlay init` and `stayfixed overlay
  upgrade` remove the old `README.md` where it still holds the text 0.1.x shipped, so `memory index
  --check` no longer reports it unreadable in every attached project; a copy you edited is kept, and
  the line says to rename it to `_README.md`. Where the overlay has no `_README.md`, as one generated
  from a 0.1.x template has not, `overlay init` writes it in the old file's place, so
  `common/memory/` is not left empty for git to drop.
- When a real `stayfixed.toml` does not load (a file or value the loader refuses, or a `[paths]`
  entry that leaves the project or passes through a symlink, such as a symlinked `AGENTS.md`),
  `stayfixed hook` now says so in its own words and points at `stayfixed docs check` for the
  detail, instead of printing `internal error` with the loader's message. The verdict per event is
  unchanged: a `PreToolUse` call is still refused, and every other event still continues open. On
  0.1.1 a refused `PreToolUse` printed that message on the stderr the model reads, and it could
  carry a key, a table name or a `[paths]` value the repository chose (plain names only: letters,
  digits, `.`, `_` and `-`, and in a path also `/`); it now prints only stayfixed's own words.
- `stayfixed attach` and `stayfixed doctor` no longer call a checkout "not the repository it was
  bound to" when the overlay records a different remote URL. URLs are compared exactly, so an https
  clone of a repository the overlay recorded over ssh (or the other way round) is a mismatch too,
  and the message now says so; `--trust-remote` still rebinds it. A checkout with no `origin` is no
  longer a mismatch at all: `attach`, `attach --check` and `doctor` called it one and pointed at
  `--trust-remote`, which then refused for the missing `origin`. The memory commands used to answer
  every binding failure with one sentence, that the overlay does not record this repository's origin
  remote for the project, and to run `stayfixed attach`. They now name the cause (no `origin` in this
  checkout, no remote recorded for the project, an unreadable record, a different remote URL, or an
  overlay root that is no longer a directory on this machine) with the way out that fits it, only a
  different remote URL points at `--trust-remote`, and a missing `origin` is said in the same words
  by the memory commands, `attach`, `attach --check`, `doctor` and the session-start line.
- `stayfixed attach` no longer leaves its machine-local files for `git status` to list. The note
  link tree, the `.codex/rules/` copies and, when `attach` writes it, `.claude/settings.local.json`
  are hidden through a marked block in the repository's own exclude file (`.git/info/exclude`,
  which every worktree shares). A path your own exclude file or global excludes file already hides
  gets no line; a committed `.gitignore` does not count, because a pull can change it. `.gitignore`
  is now written only when it does not already hide `.stayfixed/local/` and
  `.stayfixed/assessment.json`. `stayfixed detach` removes the block and gives the exclude file back
  as it was, but keeps the block while another checkout of the repository is still attached
  (`exclude_block_kept` in `--json`). It also removes the empty directories `attach` created, which
  it used to leave behind: `paths.memory`, the one above it and the harness's
  `~/.claude/projects/<slug>/`.
- `stayfixed attach` now makes every refusal before it writes anything. A repository whose
  `memory.mode` is not `overlay` used to be refused only after `.gitignore`, `.codex/rules/`,
  `.claude/settings.local.json`, the ledger and the overlay's record of the project had been written,
  and `stayfixed attach --check` exited `0` for it; both now exit `2`. A `.stayfixed`, `.codex` or
  `.claude` that is a symlink used to have `.gitignore` and more written and then stop with `internal
  error: UnsafePath`; it is now refused, naming the symlink. An overlay rule file that is not UTF-8
  and a `trust.json` that does not parse used to stop `attach` after `.gitignore` and some or all of
  the rest had been written; both are now found first. `stayfixed detach` likewise refuses, naming it,
  a `.codex`, `.claude`, `.stayfixed`, `.stayfixed/local` or `paths.memory` that became a symlink
  after the attach, before it withdraws anything; it used to stop with `internal error: UnsafePath`,
  in most of those cases after taking the settings file away. A `.claude` linked in from elsewhere
  that `attach` never wrote into no longer stops `detach` at all. When the harness memory link is held
  back until the store is approved, `attach` now says so and names the way out: run `stayfixed memory
  trust --in-repo-memory`, then `stayfixed attach` again.
- `stayfixed docs check --memory-graph` now says when there was no memory store to check, and why,
  instead of passing without a word about the graph; its exit code is unchanged.
- `stayfixed init` no longer glues its `.gitignore` region onto a last line that ends in a lone
  carriage return. git ends a line only at a newline, so it read your last pattern and the region's
  first line as one pattern, and your pattern stopped hiding anything.
- `stayfixed memory index --store <overlay>/projects/<name>/memory` now resolves the same store as a
  plain `stayfixed memory index` in the attached project, `developer` group included, and so writes
  the same `MEMORY.md`. It used to leave the developer notes out, and `--check` then called that
  index current. The same holds for every `memory` command that takes `--store`.
- `stayfixed overlay create --local` now leaves a git repository on branch `main` with no remote,
  and its last line names the two commands that give it one (`git remote add origin <url>` and
  `git push -u origin main`). It used to leave a plain directory. A directory that is already a git
  repository is left on its own branch with its own remotes, and the line says so.
- `stayfixed overlay create`, `stayfixed overlay init`, `stayfixed overlay publish-template`,
  `stayfixed attach` and `stayfixed setup` now quote what `gh`, `git`, `pre-commit` and a harness's
  plugin command print in their failure lines the way stayfixed quotes a name a repository chose: a
  line break or an escape sequence in it is escaped, so it can neither start a CI workflow command
  such as `::error::` nor drive a terminal, and an answer longer than 120 characters is cut to its
  first 120 and its length.
- `stayfixed overlay init` no longer records a plugin manifest you had edited as stayfixed's own. It
  recorded every manifest it renamed as the bytes it wrote, so an edit made before `init` (a
  description of your own, say) read as stayfixed's, and the next `stayfixed overlay upgrade`
  refreshed the file: your edit and the account suffix on its name were gone. Such a manifest is still
  renamed, and `overlay upgrade` now keeps listing it as hand-edited. `init` also reads every
  manifest before it rewrites any, so one that cannot be read stops it with none of them changed.
- `stayfixed setup --overlay create:<owner>/<name>` run again over the overlay it made no longer
  says it created the overlay: it says it found it and generated nothing, and names the files
  `stayfixed overlay init` changed there.

### Changed

- The `recommended` preset no longer carries a `[rules]` table, so the `preset-rules` session-start
  bundle is empty for it. stayfixed supports standing rules and imposes none: yours are notes with
  `metadata.startup` in your overlay's `common/memory/` or a project's memory, which the
  `standing-rules` bundle injects at the start of every session. A preset of your own that carries
  a `[rules]` table is still rendered by `preset-rules`. The machine configuration's
  `reply_language` and `artifact_language` are still recorded by `stayfixed setup`, but nothing
  reads them now: they had a meaning only through the preset's rule about which language each
  audience gets. A language preference you want followed is a standing-rule note of your own too.
- `stayfixed overlay create --template` and `stayfixed setup --overlay create:<owner>/<name>` now
  generate the overlay from `github.com/stayfixed/stayfixed-overlay-template` when you have not
  published your own `<owner>/stayfixed-overlay-template`, so an account that never ran
  `stayfixed overlay publish-template` can still create one; the fallback is looked up on
  github.com whatever host `gh` defaults to. The command names the template it used. When `gh`
  cannot say whether you have your own (an expired token, a network error, no `gh` on the
  machine), it stops with `gh`'s own message and creates nothing, instead of falling back.


## 0.1.1 (2026-09-28)

### Fixed

- The reusable workflow runs when a caller's `uses:` line names a release tag. `0.1.0`'s tag is
  an annotated one, for which the platform reports the tag object rather than the commit, so a
  caller pinned to `check.yml@v0.1.0` fails before any gate runs; pin the commit `stayfixed init`
  writes, or `@v0.1.1`. The gates are now handed the commit the tag names, which is also what an
  upgrade's `[ci] ref` is compared with.


## 0.1.0 (2026-09-28)

### Added

- **Installation.** stayfixed installs as a Claude Code and Codex plugin and as a command-line
  tool (`uv tool install stayfixed`). It needs Python 3.11 or newer on Linux or macOS, and
  imports nothing outside the standard library at runtime, so a hook works wherever `python3`
  does. The plugin ships `hooks/hooks.json`, which both harnesses read with no configuration:
  installing the plugin is enough for the guards to fire and the memory bundles to arrive at
  session start.
- **What a repository can and cannot make stayfixed do.** stayfixed treats a repository as
  untrusted input, since a clone you have not read can commit a `stayfixed.toml`, notes, a
  manifest, a `.claude/settings.json` `env` block and symlinks. Every file stayfixed replaces is
  replaced atomically and keeps its permissions. Every write into a repository walks its path
  one component at a time, refuses a symlink at any component and never leaves the project root,
  so a committed link cannot redirect a write. Your machine configuration is
  `~/.config/stayfixed/config.toml`; neither `STAYFIXED_CONFIG` nor `XDG_CONFIG_HOME` moves it,
  because a repository's settings file could set them, and `--machine` names another file
  explicitly.

  Text a repository chose (file names, note names, configuration keys and values) is never
  printed as found, so it cannot put escape sequences into your terminal or a workflow command
  such as `::error::` into a CI log. A name made of ASCII letters, digits, `.`, `_` and `-` in
  `/`-separated segments prints as itself; any other prints on a summary line as `<unprintable
  name; see --json>`, with the full name escaped in `--json`, and is quoted with control
  characters escaped in a refusal. Refusals over a configuration value name the key and the rule
  in words, never the value. Lists a repository can make arbitrarily long name at most eight
  entries and count the rest (`--json` has them all). A TOML file that does not parse is
  reported as the file and the parser's line and column only. File names that are not UTF-8 are
  handled as their own bytes, and when `git` cannot run or answer, commands say so rather than
  reading the silence as "nothing".

  Exit codes are the same everywhere: `0` success, `1` findings, `2` a refusal or an internal
  error, which a caller must never read as permission. Two exceptions are deliberate: `stayfixed
  test audit-entrypoints` exits `0` with findings, and `stayfixed hook` refuses on an internal
  error only for `PreToolUse`, so a bug in stayfixed never erases a prompt you typed.
- **Machine setup: `stayfixed setup`.** `stayfixed setup --preset recommended` writes your
  personal languages and the preset name into the machine configuration, merges the preset's
  deny rules and your personal values into `~/.claude/settings.json`, registers and installs the
  preset's plugins on every harness that declares a marketplace for them (a missing harness is a
  note, not a failure), and tells you whether `stayfixed` is on `PATH`. `--overlay <path>`
  records a private overlay you already have; `--overlay create:<owner>/<name> --yes` creates
  one on GitHub and records it. Creating a repository is the one outward-facing act `setup`
  performs and the only thing `--yes` confirms.

  Everything `setup` can refuse, it refuses before its first write. An `--overlay` path must be
  a real overlay (both `.claude-plugin/` manifests naming it `stayfixed-overlay[-<owner>]` and
  `stayfixed-overlay-marketplace[-<owner>]`) and must lie outside every checkout of the
  repository `--root` names, linked worktrees included. The machine configuration is merged key
  by key: a value you or an earlier run recorded is never overwritten by a preset default, and
  unknown tables are carried through, but comments do not survive the rewrite. A
  `~/.claude/settings.json` reached through a symlink (stow, chezmoi, a synced home) is refused
  rather than written through; the refusal names the link, and `--settings <path>` writes the
  file where it really is. `--home` and `--machine` point a run at a scratch destination; they
  are not a dry run.

  `stayfixed setup --git-hooks` installs the commit-message hook into this repository's own
  hooks directory, never `core.hooksPath`. An existing hook is kept as
  `prepare-commit-msg.local` and chained to, and `--git-hooks --uninstall` restores it exactly.
- **Starting a project: `stayfixed init`.** `stayfixed init --questions` prints the six values
  `stayfixed init --yes` would take (name, base branch, agents, profile, memory mode, files kept
  out of git), where each came from and the flag that replaces it (`--name`, `--base-branch`,
  `--agent`, `--profile`, `--memory-mode`, `--local`); under `--json` it is a JSON Schema. `init
  --yes` writes the footprint: `stayfixed.toml`, a `CLAUDE.md` pointing at whatever `[paths]
  agents_md` names, an `AGENTS.md` skeleton (or a managed section in an existing one) stating
  your effective budgets, a `.gitignore` block, the documentation skeleton the other commands
  expect, and a CI workflow calling the reusable gate pinned to the commit of the stayfixed
  release that wrote it. Every file is recorded in `.stayfixed/manifest.json`. `--dry-run` shows
  every file first, and a refusal anywhere writes nothing. A file already present, an existing
  `CLAUDE.md` included, is left alone. `init` runs once per repository; after that, use
  `stayfixed upgrade`.

  The base branch comes from `origin/HEAD` only when that names a plain branch under
  `refs/remotes/origin/`, otherwise it is `main`. With no remote, it is the branch checked out.
  A repository whose remote has no `origin/HEAD` (created locally and pushed, or whose only
  remote is `upstream`) gets `main`, never the branch you are on; a `note:` line names
  `--base-branch` and, for `origin`, `git remote set-head origin --auto`.

  A `stayfixed.toml` you wrote by hand is read as the answers, not replaced: `init` adds at most
  a missing `[stayfixed] version`, refuses a file the next command could not load, and names the
  custom gates it configures, whose commands `stayfixed assess` runs unless given `--builtin`.
  The workflow is rendered from the `[ci] ref` your file records, so a file with no ref gets no
  workflow: write a released commit into `[ci] ref` before `init`, or run `stayfixed upgrade`
  afterwards. `--no-ci` writes no workflow and records `[ci] mode = "none"` when this run writes
  the file. When no released tag matches the running version, or the public repository cannot be
  reached, the workflow is skipped with a sentence saying why and which command can still act.

  The first stack profile is `python`. When `[stayfixed] profile` names it (from `--profile`, or
  detected), `init` writes its rules once to `docs/stayfixed/rules/python.md`, the copy the
  project edits; every harness reading `AGENTS.md` gets a pointer and the profile's must-know
  lines, and Claude Code also a path-scoped pointer under `.claude/rules/`. `stayfixed assess`
  runs the profile's eight checks: a lockfile committed or deliberately ignored,
  `requires-python` declared without a cap, one type checker configured, strict pytest markers
  in whichever file pytest reads, marker selection kept out of `addopts`, and Ruff's defaults
  not hidden by a legacy `select`.
- **Keeping the footprint current: `stayfixed upgrade` and `stayfixed uninstall`.** `stayfixed
  upgrade [--dry-run] [--force PATH]` refreshes untouched files after a stayfixed update; files
  you edited, and files stayfixed never wrote, are skipped and named, and `--force` with a path
  overwrites that one. `[stayfixed] version` moves in place, every other byte of
  `stayfixed.toml` kept. When the workflow pins a commit, `[ci] ref`, the pin and the version
  move together or not at all; a `[ci] ref` that is not a commit is left alone. A caller
  workflow you edited is reported `skip_modified`, and `upgrade` then holds the version and
  `[ci] ref` until `--force .github/workflows/stayfixed.yml` or a hand edit brings it in line. A
  project recording a newer stayfixed (a pre-release included) or a version stayfixed cannot
  order is refused. Each run decides first and writes second, so a dry run shows exactly what a
  real one will do; a run stopped by a failed write keeps and records what it did, and the next
  run continues.

  `stayfixed uninstall [--dry-run] [--force PATH]` removes files whose bytes are still
  stayfixed's, takes stayfixed's sections out of files holding other text (shown as `(retired;
  stayfixed's part only, the file stays)`), removes the manifest, and keeps and lists every file
  you edited. It refuses while `.stayfixed/local/` holds notes or edited files, and while the
  manifest records a `stayfixed.toml` that is missing. A `stayfixed.toml` you wrote before
  `init` stays.

  `[artifacts] local` keeps chosen artifacts out of git: they are written under
  `.stayfixed/local/artifacts/`, recorded in `.stayfixed/local/artifacts.json`, refreshed while
  unchanged and never overwritten once edited. It cannot name `config` or `gitignore`. `init`,
  `upgrade` and `uninstall` also refuse, before writing, a `[paths]` layout that aims two
  artifacts at one file (paths differing only in case count as one) and a `[paths]` value
  pointing at an existing file git ignores, such as a `.env`.
- **The `stayfixed.toml` grammar.** The configuration is committed and repository-controlled, so
  it is a closed grammar: unknown sections and keys are refused, and a file that looks valid can
  be refused on the rules below. Each refusal names the key and states the rule.

  `[paths]` values are plain relative paths: segments of letters, digits, `.`, `_` and `-`
  joined by single `/`, none empty, `.` or `..`. A leading `./`, a doubled `//` and a trailing
  `/` are refused, not normalised (except in `ledger.code_roots`, where `"./src"` and `"src/"`
  read as `src`). No value may contain a `.git` component, at any depth or case, or point inside
  `.stayfixed/`; `.github/` and `.gitignore` are unaffected. `[paths] stayfixed` (default
  `docs/stayfixed`) is where stayfixed's own project files go.

  `[project] name` and custom gate names are one lowercase path segment of letters, digits, `.`,
  `_` and `-`, led by a letter or digit. `[project] base_branch`, `release_branch` and `[ci]
  gate_branch` use letters, digits, `.`, `_`, `-` and `/`, led by a letter or digit, and never a
  name git refuses; `release/2.0` is accepted, a name with `+`, `@`, a leading `_` or a
  non-ASCII letter is not. `[ci] gate_branch` defaults to `[project] base_branch`. `[stayfixed]
  preset` is matched exactly, case included, against the shipped presets, and `profile` must be
  a shipped profile. `[stayfixed] state`, `[memory] mode` and `[ci] mode` take only their listed
  values. `[ci] ref` is the full-length commit sha of a released stayfixed tag. Each
  `memory.groups` entry names a subdirectory of `paths.memory` (`""`, `"."` and doubled or
  trailing slashes are refused); a duplicate counts once.

  `[gates]` names the gates a project runs: the built-in `docs`, `bugs`, `plan`, `commit` and
  `trail` by default, and argv commands under `[gates.custom.<name>]`. `[stayfixed] enforced`,
  written by `stayfixed adopt promote`, lists the gates promoted so far; an `installed` project
  whose `enforced` lists only some gates is refused.

  **A `stayfixed.toml` that is a symbolic link is refused by every command**, before anything is
  read through it, and while it is one every agent tool call in that checkout is refused at
  `PreToolUse`. Replace the link with the file.
- **Working memory: `stayfixed memory`.** Notes are Markdown files with frontmatter; `MEMORY.md`
  is a routing index generated from them. Session-start bundles arrive whole: a bundle too large
  for its slot is withheld with a notice rather than cut in half, and `stayfixed memory fit`
  says what fits. In a git worktree the store is linked in, not copied, and every link goes
  through the same contained walk as a file write. `stayfixed memory refs` reports backticked
  repository paths in your notes that no longer exist.

  Notes committed to a repository you cloned reach the model only after `stayfixed memory trust
  --in-repo-memory`, and then inside a marked region that says they are data. When the
  repository changes what it ships, you are asked again, and the harness's link to the store is
  withdrawn until you are. Notes in your own overlay need no approval.

  `stayfixed memory session-context --bundle index` emits `MEMORY.md` on Codex only, since
  Claude Code reads it natively; the harness is read from the environment, so the same command
  answers differently in each. The `recommended` preset's five standing rules (ask at a decision
  fork, work in a worktree by default, keep research sources within two months, read CI after a
  push, split languages by audience) arrive at session start through the `preset-rules` bundle;
  they are never repository content and need no trust record.
- **The private overlay: `stayfixed overlay`.** An overlay is your own repository of standing
  rules, cross-project notes and one record per bound repository. `stayfixed overlay create`
  renders one locally with `--local` (no network call) or on GitHub with `--template`, private
  from the start; neither is a default, so an omitted flag never creates a repository on your
  account. `--template` generates from `<owner>/stayfixed-overlay-template`, which `stayfixed
  overlay publish-template` publishes from your own authenticated checkout. Without `--yes`,
  `publish-template` only reports what it would create, mark and push; a same-named repository
  that is not public is refused rather than flipped, and a `gh` or `git` that cannot answer is
  reported as such, not as "nothing to push".

  `stayfixed overlay init` names the overlay after you in all three plugin manifests so two
  overlays never collide, and installs a commit-time secret scan beside the template's push-time
  one, whose GitHub Actions are pinned at full commit shas and kept current by
  `.github/dependabot.yml`. `stayfixed overlay upgrade` refreshes files you have not edited and
  always names the two files that can grant a capability, permission rules and hook entries,
  whatever their hashes say; run `--dry-run` first to see that list before anything changes. The
  shipped template has deny-only permissions and no hooks. Both commands refuse a `--root` that
  is not an overlay. An overlay may declare the stayfixed it needs as `stayfixed.requires` in
  its plugin manifest, each version component at most nine ASCII digits.
- **Binding a repository: `stayfixed attach` and `stayfixed detach`.** `stayfixed attach --store
  <overlay>/projects/<name>/memory` checks that the overlay recorded this repository's remote
  (`--trust-remote` accepts a different one), prints the permissions and hook entries the
  overlay would add, merges them into `.claude/settings.local.json`, copies your Codex rules
  into `.codex/rules/`, and links your notes into the checkout and every worktree. `--check`
  reports the same and writes nothing. Every refusal `attach` can foresee happens before its
  first write: `--store` must be your overlay's directory for this project, since the overlay
  root comes from your machine configuration and never from the path you type; a new permission
  needs `--yes`; `--machine` is accepted only from an interactive shell; a note group that is
  still a real directory must be moved into the overlay first (`--check` counts them); and a
  `~/.claude` that is a symlink into a dotfiles tree is refused by name, here, in `detach` and
  in the worktree session hook. Make that directory real and let your dotfiles manager adopt the
  files inside it.

  `stayfixed detach` removes exactly what `attach` added, from a ledger under
  `.stayfixed/local/`, and leaves the overlay's binding record so a re-attach does not ask
  again. Run it from the checkout you attached from. The ledger is never an authority: a field
  `attach` could not have written is refused with nothing removed. Directories `attach` created
  are removed only when empty, except the note link directory, and on a repository `stayfixed
  init` set up the `.gitignore` block stays. The overlay's own `hooks/hooks.json` stays empty;
  its hook entries reach a repository only through `attach`'s explicit merge.

  In a repository with `[memory] mode = "overlay"`, a session hears once at its start what
  stands between it and its notes: no overlay recorded, not attached, a different remote, a
  group still a real directory, an overlay requiring a newer stayfixed, or, when nothing else is
  wrong, a branch with no upstream or unpushed commits and uncommitted changes. Each line is
  fixed text naming the command to run; a healthy repository hears nothing. On a compaction the
  unpushed-work check is skipped, so an overlay that becomes unpushed mid-session is reported at
  the next start or resume, or by `stayfixed doctor`.
- **The bug ledger: `stayfixed bugs`.** One Markdown file per bug under the directory
  `stayfixed.toml` names, plus a generated index that is a pure function of those files and
  refuses to delete content it did not write. `stayfixed bugs check` holds every entry to a flat
  frontmatter contract, every high-severity entry to a filled evidence-boundary line, and every
  identifier under your code roots to an existing entry. `stayfixed bugs new` files an entry at
  the next number free across every branch this checkout can see, and warns when it could not
  read that history. `stayfixed bugs renumber` moves an entry and every reference, leaving a
  pointer at the old number. Entries are append-only: with `--base`, which the `bugs` gate
  passes, a deleted ledger is a `ledger-removed` finding and a deleted or renamed entry an
  `entry-removed` finding, and a branch is not blamed for an entry filed after it forked.
- **Documents and plans.** `stayfixed docs check` holds your always-loaded agent document and
  the roadmap's prose to the preset's budgets (a project may lower them, never raise them),
  checks that every local link resolves, and advises, without failing, on broken or repeated
  wiki-links and bracketed bug identifiers in the memory store. `stayfixed docs trail`
  regenerates the design-and-plan listing in your roadmap from the tracked documents and a
  `trail.toml` you own, and will not let a renamed or new document claim it shipped. A
  `trail.toml` theme `pattern` accepts only literal text, `.`, `.*`, `|`, `^`, `$` and `\`
  before punctuation, at most 256 characters, with at most 32 themes; other syntax is refused.
  Inside a git work tree, `docs trail` writes nothing and exits `1` when `git` cannot say which
  documents are ignored, so a local-only document never reaches the committed roadmap.

  `stayfixed plan check` lints the plans a change touches: every path they name exists, no
  verification step presumes its answer, and a mutation's outcome stays an expectation until
  someone has watched it. It lints every plan the merge could alter, across all merge bases. The
  README places stayfixed beside the tools it sits next to and says what each command writes,
  and `docs/methodology/` states the ten principles behind it with dated sources.
- **Hooks and guards.** The hook wrapper finds a Python 3.11 or newer, runs from your project
  root, and refuses with a named `SF_*` token rather than letting a broken guard read as
  permission. Its environment may say where something goes, never which program runs:
  `STAYFIXED_PYTHON_CANDIDATES` is honoured only from an interactive terminal, because a
  committed `env` block applies without a trust prompt; no `python3` inside any checkout of the
  repository is ever run, however `PATH` reached it; and `git` comes from a fixed list of
  absolute paths, never `PATH`. If your only Python 3.11 lives inside your checkout, you will
  get `SF_NO_PY` and a red `wrapper` row in `stayfixed doctor` with the remedy.

  The `PreToolUse` guard (also runnable as `stayfixed guard bg-cleanup`) refuses a backgrounded
  command that would leave an `&` job running past the harness's reap or that begins with
  `sleep`. It advises when a restore line may never be reached, and when a backgrounded command
  ends in `; echo …`, which makes the reported exit code the echo's. `stayfixed commit check`
  fails a pull request whose commit messages carry an AI attribution trailer; `stayfixed commit
  strip`, run by the hook `setup --git-hooks` installs, removes one before the commit exists.
  `stayfixed test hygiene` names the two environment faults that make a red run unattributable,
  and `stayfixed test audit-entrypoints` lists tests that never exercise what they name.

  `stayfixed test attribute --command CMD` decides whether a failing test is your change or your
  environment. It runs the command on the working tree, on `HEAD`'s committed tree and on the
  merge base with your base branch (the last two extracted with `git archive` into a scratch
  directory) and prints the verdict the three exit codes give. It never moves your checkout, but
  the first run does execute your command in your working tree. Put your environment sync in the
  command (`uv sync --locked && uv run pytest …`). With several merge bases it reports the
  attribution as undetermined and runs nothing.
- **Assessing and adopting: `assess`, `gate` and `adopt`.** `stayfixed assess` inventories what
  stands between a repository and enforcement: every configured gate and what no gate runs, such
  as marker comments, tracked `.env` files, committed notes, foreign hooks and workflows, a
  CODEOWNERS file that leaves a workflow or the rest of `.github/` without an owner, commit
  subjects outside the vocabulary, and the profile's checks. The inventory goes to
  `.stayfixed/assessment.json` and `--json`. A gate that could not judge the tree is `could not
  run`, never a finding; when the base is not in the checkout, the summary says why `plan`,
  `commit` and `bugs` could not run and suggests `--base refs/heads/<base_branch>`. `--builtin`
  on `assess`, `gate` and `adopt promote` runs none of the commands `[gates.custom]` names, for
  a clone whose commands you have not agreed to run; without it those commands run, as the
  repository's test suite would.

  The `docs` and `trail` gates judge tracked files, because CI checks out nothing else. When a
  file they read is on disk but untracked, or tracked under a name differing only in case,
  `assess` reports the gate as unable to judge the tree as CI will and `adopt promote` does not
  enforce it. Commit the file, or remove the gate from `[gates] builtin`.

  `stayfixed gate` is the pull-request gate, runnable locally. It reads the base's
  `stayfixed.toml` at an exact commit, runs the configuration check and every configured gate,
  advisory or enforcing, and prints the verdict. A pull request may only tighten: enforce more
  gates, move the state forward, add a gate, drop or re-command one the base does not enforce,
  lower a budget; the preset, profile, harnesses and project name are free, and an upgrade may
  move the version to the running stayfixed and the pin to a released commit. While the base
  enforces any gate, any other change is refused and lands only by a direct push to the base
  branch. A project's first pull request, with no `stayfixed.toml` on the base, is judged by the
  tree's copy. A custom gate runs only the command the base gives it, so one a pull request adds
  or changes is not run until it lands; the base's enforced custom gates run first, no custom
  gate starts once the run has failed, and each command runs in its own process group.

  `stayfixed adopt begin PLAN` starts an adoption with a plan that passes `plan check`.
  `stayfixed adopt promote [GATE…]` enforces the named gates together once they pass, or, with
  no names, every gate that passes now; when all enforce, the project is `installed`. A custom
  gate is promoted only once the base branch has its command.
- **The reusable CI workflow.** Your CI calls stayfixed's gates through one reusable workflow
  pinned at a commit sha; `stayfixed init` writes the caller, `.github/workflows/stayfixed.yml`.
  One `gates` job runs `stayfixed gate` with no resolver and no build backend, in two steps: the
  configuration check and built-in gates, then your `[gates.custom]` gates only if the first
  step passed, so no command your repository wrote runs where the verdict is decided. Python
  starts as `python3 -P -s`, so no module in the checkout and no user-site `.pth` file loads.
  Custom gates run on the bare runner image and install their own toolchain.

  The caller runs only for pull requests into the gate branch, re-runs when one is retargeted,
  reports for that branch's merge queue, and passes the branch as a literal `base:`, so a check
  cannot be won against a looser branch and then retargeted. The base resolves to a commit from
  `refs/remotes/origin/<base>`, so a tag of the same name cannot stand in for it, and the
  stayfixed that runs is checked against the commit your `uses:` line pins before any gate runs.
  The tree under review cannot turn off the gates it faces, but the caller file is one a pull
  request can edit, so protect `.github/` with code-owner review as usual. The `only` input runs
  a chosen few gates (the configuration check always runs), and `timeout-minutes` sets the job
  limit, 15 by default, a whole number from 5 to 60; any other value fails the job, and a job
  that times out is cancelled, never passed.
- **Diagnosing an installation: `stayfixed doctor`.** Sixteen checks over the configuration, the
  hook wrapper, the overlay binding and memory path, every hook entry with its provenance,
  budgets, bundle fit, the overlay's secret scan and the stayfixed version it requires, the note
  store, recent hook failures, `[ci] ref`, and ignored environment variables. It writes and
  repairs nothing; every finding carries the command that fixes it, and `--json` carries all
  sixteen. It exits `1` when any check is red; a `skip` never reaches the exit code. The `files`
  row compares the installed wrapper, hook table and launcher with the hashes the release
  shipped, and says whether a file is modified, absent or unrecorded. The `ci-ref` row checks
  that `[ci] ref` is a released commit and matches the workflow's pin; a missing workflow under
  `[ci] mode = "reusable"` is a warning.

  `doctor --json` is relayed to a model, so no repository-authored text reaches it: hook entries
  are named by position, the hook log is counted and never quoted, and a file it cannot read is
  a warning naming the file, not a red row a clone could force. It reads the workflow only as a
  regular file up to 256 KiB, bounds its one network call at 30 seconds, runs only the hook
  wrapper of its own installation, and trusts the overlay's record over a ledger a clone could
  commit.
- **Skills and agents.** The plugin ships `close-bug` and `memory-sweep`; six procedures an
  agent can be handed (`file-bug`, `sweep-defect-class`, `review-plan-three-lenses`,
  `attribute-failure`, `run-correctness-audit`, `retro-to-guard`); short wrappers for `init`,
  `upgrade`, `uninstall`, `attach`, `setup` and `doctor`; and a read-only `code-navigator`
  agent. Every `stayfixed` invocation in a skill is checked against the real parser. The `init`
  skill asks what `stayfixed init --questions` lets you answer, shows the dry run, writes only
  on an explicit yes, and then starts the adoption (`stayfixed assess`, a plan, and `stayfixed
  adopt begin` on a second explicit yes). Silence, a timeout or an empty answer is never a yes.
  If you decline to run the repository's own gate commands, it uses `--builtin`.
- **Release tooling for this repository.** `stayfixed release` is stayfixed's discipline for its
  own repository, not something it asks of yours. `release check` holds one version across
  `pyproject.toml`, `uv.lock`, the package, both plugin manifests and `CHANGELOG.md`, with
  `--tag` adding the tag and treating a pending changelog fragment as a finding. `release notes
  --version X.Y.Z [--draft]` assembles `CHANGELOG.md` through towncrier. `release hashes`
  records the sha256 of the three files a harness runs in `hooks/hashes.json`, which `release
  check` verifies on every run and `stayfixed doctor` reads on your machine.

### Known limitations

- No moving `v1` alias exists for the reusable workflow during `0.x`, because a `0.x` minor may
  break what came before. Pin the full commit `stayfixed init` writes; `stayfixed doctor`
  reports a `[ci] ref` of `v1` red until the first `1.x` release creates it.
- The `uvx` form of the gate is not shipped yet.
- Windows is not supported: path containment relies on `openat` with `O_NOFOLLOW` and
  `O_DIRECTORY`.
- Ending a custom gate's process group does not end a descendant that left it (a new session or
  a job-control shell's own group) or one stayfixed may not signal (a `sudo` or setuid
  descendant). The base's enforced custom gates share one checkout; only a matrix leg per gate
  separates them.
- A shallow clone cannot be judged by the `plan` and `bugs` gates or by `stayfixed test
  attribute`: use a full-depth checkout.
- Each area's `api.py` is its only supported Python import surface; other names may move without
  notice.
