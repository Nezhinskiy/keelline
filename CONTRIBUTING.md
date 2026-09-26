# Contributing to Keelline

Keelline's real conventions used to live only inside `docs/plans/`, which meant a first-time
contributor's pull request could be rejected on rules they had no way to read. This file is
those rules.

## The short version

```bash
uv sync                                           # once
uv run pytest -n auto --cov --cov-fail-under=92   # the suite across workers, at CI's floor
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run python scripts/mutation_oracle.py          # every declared mutation still reddens
uv run keelline release check                     # version discipline
```

All five run in CI on Linux for Python 3.11, 3.12 and 3.13, and on macOS for 3.13 — including
the mutation oracle, which is this project's headline obligation and not an optional extra, and
the coverage floor, which is why `pytest -q` alone will give you a green tree and a red pull
request. CI runs three more steps you can reproduce only from a build (`uv build`, then
`scripts/check_artifacts.py dist` and an installed-wheel render) and one job you cannot
reproduce without a global install of the harness CLI, the plugin-manifest validator; a failure
in either is ours to diagnose, not yours.

## What this project is, and what that costs a change

Keelline treats **a repository as untrusted input**. A clone can commit a `keelline.toml`, a
`MEMORY.md`, a manifest, an `env` block and a tree of symlinks, and all of it reaches the code
before a human has read any of it. Three rules follow, and a change that breaks one will be
sent back however good it looks otherwise.

**The runtime imports only the standard library.** Hooks run under whatever `python3` the
wrapper finds, before any environment exists, so a third-party import works on your machine and
fails inside a hook on somebody else's. `tests/test_import_boundary.py` enforces this on every
supported interpreter. Development dependencies (`pytest`, `ruff`, `mypy`, `towncrier`) are
fine; a runtime one is not.

**Writes go through `fsops`.** `config.paths.contained()` decides whether a configured path
*may* be written — it gives a user-facing refusal and catches a committed symlink — and
`fsops.write_within` / `mkdirs_within` / `remove_within` then do the write through an
`O_NOFOLLOW` walk, so a component that becomes a symlink after the check cannot redirect it.
Do not add a `Path.write_text`, a `mkdir(parents=True)` or an `os.replace` on a string path to
a lane that puts files into a repository.

**Repository bytes are data.** Anything a repository authored — a note, an index line, a
`memory.groups` entry, a refusal message built out of one — reaches the model only inside
`trust.wrap`'s delimited region, and only after `keelline memory trust`. If you find yourself
putting such a string into a `Result.summary`, a `HookResult.context` or an exception message,
wrap it.

## Areas

An area is a subpackage of `src/keelline/` that the CLI frame and the hook registry discover by
name — there is no shared registry to edit.

Today the discovered ones are `attach`, `docs`, `doctor`, `guards`, `hooks`, `ledger`,
`memory`, `overlay`, `project`, `release` and `setup`. Three arrived with the install path:
`overlay` renders and upgrades the private overlay, `attach` binds a repository to one and
unbinds it again, and `doctor` reports on what every other area left behind and repairs none
of it. `project` is the eleventh: it holds the shipped project templates and `init`, the
command that writes a repository's footprint from them.
(`config`, `presets`, `profiles`, `scaffold` and `templates` are subpackages and not areas, and
`harnesses` is a module — nothing discovers them, because they carry neither a `commands.py`
nor a `hooks.py`.)

- `commands.py` with a `register(groups)` gives the area its CLI group.
- `hooks.py` with a `register() -> list[Handler]` gives it hook handlers. Every import inside a
  handler body, never at module level: `tests/test_areas.py` asserts that discovery in a clean
  interpreter imports neither the configuration layer nor the presets.
- `api.py` is the area's import surface. Other areas import from it and from nothing else, and
  its `__all__` must equal exactly what it imports — a test parses the file and checks, and
  `tests/test_areas.py` walks every module under `src/keelline/` and fails on a cross-area
  import that reaches past one. The list is what consumers actually reach for, not what the
  area finds tidy: a lane that needs something absent from it grows it deliberately, in a commit
  that says which lane and why. `cli.py` is the CLI frame rather than an area, and its one
  direct import of `hooks.policy` is named in that test rather than skipped silently.
- **`keelline.hooks.api` is the one exception, and it is structural rather than drift.** That
  module *defines* the vocabulary two areas share — `EVENTS`, `Policy`, `Decision`, `HookEvent`,
  `HookResult`, `Handler`, `Sink`, `NullSink`, `detect_harness` and the sink's on-disk layout —
  instead of re-exporting it, because `hooks.dispatch`, `hooks.sink`, `hooks.registry` and every
  area's `hooks.py` import *it*: a name defined in one of those modules and re-exported from
  `api.py` would be an import cycle, not a tidying. So in the one area that ships the common
  vocabulary the rule runs the other way — **a name two areas share is defined in `api.py`** —
  and its `__all__` lists what it defines. No other area may read this as licence: a consumer
  still imports `keelline.hooks.api` and never `keelline.hooks.dispatch` or `.sink`.
- Every area is a regular package with an `__init__.py`. `pkgutil.iter_modules` does not yield a
  namespace package, so one without it is invisible to both discovery paths.

Two top-level trees are documents rather than areas. `skills/` holds the Agent Skills this
plugin ships and `agents/` the agent files; [skills/README.md](skills/README.md) is their
contract — a skill body is **action language** and never names a harness tool, a `SKILL.md` is
capped at 80 lines with the detail in `<skill>/references/`, and every `keelline …` invocation
in a skill must parse against the real parser or be listed in `NOT_YET_SHIPPED` against the
package that will ship it. `tests/skills/test_skills.py` holds all three, and the lane that
ships a command deletes its `NOT_YET_SHIPPED` entry.

## Tests

**Every new assertion ships with the mutation that reddens it, or a sentence saying why none
exists.** This is the project's strongest test convention and the easiest to satisfy vacuously:
write the assertion, break the line of source it is about, watch it fail, put the source back.
Say what you broke, in the test's own comment or in the commit message.

For a guard that is genuinely load-bearing — a containment check, a trust gate, a refusal that
something downstream reads as permission — add it to `mutations.toml` instead of only describing
it, and the check becomes reproducible:

```bash
uv run python scripts/mutation_oracle.py            # every declared mutation
uv run python scripts/mutation_oracle.py fsops      # only the matching ones
uv run python scripts/mutation_oracle.py --jobs 2   # at most two entries at a time
```

Each entry names one file, one exact line to change, and the tests that must fail when it does.
The keys are `name`, `file`, `before`, `after` and `reddens` — `reddens`, not `tests`, and
`name` is required: the oracle raises `KeyError: 'name'` on an entry without one. `before` is an
exact substring of the file and `after` is what replaces it, so an entry whose `before` has
drifted is a finding rather than a skip. The oracle proves `HEAD`: it applies every
mutation to a throwaway worktree, so it never writes your working tree, and it refuses when a
mutated file — **or any test file that a selected entry's `reddens` names** — has uncommitted
changes, because that edit is work the run cannot see. Which is why a mutation run comes
*after* the commit it is about, and why an uncommitted test edit mid-change stops it too.

The oracle proves several entries at once: one worktree per job, each job proving one entry at
a time in a checkout no other job touches, with as many jobs as the process has CPUs up to four
unless `--jobs` says otherwise. So a test that a `reddens` names runs beside other tests in
other processes and must be safe to — no shared path outside `tmp_path`, no wall-clock bound
that load could break. A test that fails under contention fails on the mutated run for a reason
that is not the mutation, and that reads as *caught*.

```toml
[[mutation]]
name = "the containment walk stops refusing '..'"
file = "src/keelline/fsops.py"
before = "        if part in (_PARENT, _HERE):"
after = "        if part in (_HERE,):"
reddens = ["tests/test_fsops.py::test_a_parent_component_never_leaves_the_root"]
```

The oracle sweeps before it runs. A killed run — `kill -9`, a CI timeout, a cancelled agent —
cannot run its own cleanup, and `git worktree prune` does not collect what it leaves: prune only
drops entries whose directory is gone, and a killed run leaves its directory standing. So the
first thing a run does is drop every `keelline-oracle-*` checkout but its own, naming on stderr
what it dropped.

CI runs the whole set in a job of its own, called `oracle`, on one configuration —
`ubuntu-latest` with Python 3.13 — while the tests go on running on all four. The oracle proves
that a mutation reddens a test, which is a property of the code and of the tests rather than of
the platform, and at 657 to 751 s a run it was 76% of the `checks` job and had pushed it past
its fifteen-minute bound. Its own job has its own budget, and `ci.yml` says what that budget
buys in further entries; `test_the_mutation_oracle_has_a_job_of_its_own_with_a_budget_that_fits`
reddens when the set outgrows it, so you find that out here rather than from a cancelled job.

Say plainly what narrowed: your local run is still the full check, and CI's guarantee is now
that the set holds on Linux under 3.13. A mutation that holds there and not on macOS would
reach `main`, where before it would have been caught in the pull request.

Four things are findings: a mutation that *survives*; one whose `before`
line no longer exists, because the assertion and the line it is about have drifted apart; one
whose `before` line appears more than once in the file, because then the entry does not name a
line; and one whose named tests do not pass on a clean tree before the mutation is applied,
because a test that is red, skipped or misspelled cannot prove anything about a guard. A fifth is
not a finding about your entry but about the mutation you chose: one that stops the named tests
from *running* — an `after` that breaks the import, say — is reported as proving nothing, because
pytest's non-zero exit there says only that something went wrong. This is not a coverage
substitute; `--cov` is the breadth measure. It is the set of guards whose load-bearingness has
to be proven rather than merely executed, which is exactly the distinction that let
`fsops.open_within` be covered by twelve tests and contain nothing.

Writing the oracle found two entries that did not hold, which is the argument for having it.

Name a test after the behaviour, not the function:
`test_a_corrupt_record_is_never_overwritten`, not `test_recorded`.

Comment *why*, in the test. Most of this suite's comments name the defect the test exists to
catch, which is what makes a later reader able to tell a load-bearing assertion from decoration.

**The neutrality gate walks every tracked file.** `tests/test_neutral.py` holds the whole tree
to a denylist and three shape rules: no string that identifies the repository these guards were
extracted from, no personal email address, no bare abbreviated commit id, no vendor-prefixed
branch name (`codex/…`, `claude/…`, `cursor/…`). The denylist is stored as digests rather than
as the strings, because a gate that lists what it is hiding publishes it in the very repository
the rule is about — so a hit reads `token be440e8c9338 at 812` and not the word you wrote.

```bash
uv run pytest tests/test_neutral.py
uv run pytest "tests/test_neutral.py::test_no_tracked_file_carries_a_project_identifying_string[docs/cli.md]"
```

The second form is how you ask about one file: the walk is parametrised and the case id is the
file's own path from the repository root.

The number after `at` is the character offset of the first matching window in the lower-cased
file, and the entry's own length is what you read from there: slice that many characters out of
your file at that offset and you are looking at the string the gate refused. Characters and not
bytes, because the sentence before this one is the instruction and an em dash is three bytes:
the gate used to report the byte offset, and on a line in this repository's own house style the
two differed by four. Two entries are four characters long, which is why the offset is printed
at all — a four-character window is not something a contributor can guess. Rewrite the line;
do not add an entry to the exemption.

A test must never read or write the developer's real `~/.config/keelline/`, `~/.claude/` or
`~/.codex/`. Pass `--machine` to a command, `machine=` to `resolve`, `home=` where a function
takes one, and use `tmp_path` for everything else. A test must not shell out to `gh`, `claude`,
`codex` or `pre-commit` either: `overlay.api.Runner` is the seam those calls go through, and a
stub records the argv, which is the part of them that can be wrong in a way somebody notices.

## Commits and changelog

Conventional-commit subjects (`feat(memory):`, `fix(scaffold):`, `docs(plans):`), describing
**intent** rather than mechanics. `fix(memory): stop a half-built worktree tree and a refusal
from vanishing` is the house style; `fix: update worktree.py` is not.

User-visible changes need a towncrier fragment in `changelog.d/`, named
`+<slug>.<type>.md` where type is `feature`, `fix` or `change`. The leading `+` is towncrier's
orphan prefix, and it is not decoration: without it towncrier reads the slug as an issue
reference and prints it in parentheses at the end of the bullet, so the release notes everyone
reads would carry the project's internal lane vocabulary. Write the fragment as a release note
someone outside the project can read — not as a note to yourself about the lane.

`uv run keelline release check` cross-checks the version across `pyproject.toml`, `uv.lock`,
the package, and both plugin manifests. It runs in CI; run it before you push.

## Plans

Substantial work is planned first, in `docs/plans/YYYY-MM-DD-<slug>.md`, against the extraction
design. That design document is not public yet — it lives in a private repository — so a plan's
references to it cannot be followed from here. You do not need a plan for a bug fix or a
documentation change; open an issue or a pull request and say what you found.

The delivered plans in `docs/plans/` are a record, not a work list. Their `**Interfaces:**`
blocks are kept current and are what a later lane builds against; their code blocks are
as-planned and may differ from what shipped.

## Security

Do not open a public issue for a containment bypass or a trust-gate bypass. See
[SECURITY.md](SECURITY.md).

## Code of conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
