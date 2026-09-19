# Contributing to Keelline

Keelline's real conventions used to live only inside `docs/plans/`, which meant a first-time
contributor's pull request could be rejected on rules they had no way to read. This file is
those rules.

## The short version

```bash
uv sync                         # once
uv run pytest -q                # the suite
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run keelline release check   # version discipline
```

All four run in CI on Linux for Python 3.11, 3.12 and 3.13, and on macOS for 3.13. CI also
measures coverage and fails below 92%.

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
`memory`, `overlay`, `release` and `setup`. Three arrived with the install path: `overlay`
renders and upgrades the private overlay, `attach` binds a repository to one and unbinds it
again, and `doctor` reports on what every other area left behind and repairs none of it.
(`config`, `presets` and `scaffold` are subpackages and not areas — nothing discovers them,
because they carry neither a `commands.py` nor a `hooks.py`.)

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
uv run python scripts/mutation_oracle.py          # every declared mutation
uv run python scripts/mutation_oracle.py fsops    # only the matching ones
```

Each entry names one file, one exact line to change, and the tests that must fail when it does.
The keys are `name`, `file`, `before`, `after` and `reddens` — `reddens`, not `tests`, and
`name` is required: the oracle raises `KeyError: 'name'` on an entry without one. `before` is an
exact substring of the file and `after` is what replaces it, so an entry whose `before` has
drifted is a finding rather than a skip. The oracle proves `HEAD`: it applies every
mutation to a throwaway worktree, so it never writes your working tree, and it refuses when a
mutated file has uncommitted changes, because that edit is work the run cannot see — which is
why a mutation run comes *after* the commit it is about.

```toml
[[mutation]]
name = "the containment walk stops refusing '..'"
file = "src/keelline/fsops.py"
before = "        if part in (_PARENT, _HERE):"
after = "        if part in (_HERE,):"
reddens = ["tests/test_fsops.py::test_a_parent_component_never_leaves_the_root"]
```

CI runs the whole set. Three things are findings: a mutation that *survives*; one whose `before`
line no longer exists, because the assertion and the line it is about have drifted apart; and
one whose named tests do not pass on a clean tree before the mutation is applied, because a test
that is red, skipped or misspelled cannot prove anything about a guard. This is not a coverage
substitute; `--cov` is the breadth measure. It is the set of guards whose load-bearingness has
to be proven rather than merely executed, which is exactly the distinction that let
`fsops.open_within` be covered by twelve tests and contain nothing.

Writing the oracle found two entries that did not hold, which is the argument for having it.

Name a test after the behaviour, not the function:
`test_a_corrupt_record_is_never_overwritten`, not `test_recorded`.

Comment *why*, in the test. Most of this suite's comments name the defect the test exists to
catch, which is what makes a later reader able to tell a load-bearing assertion from decoration.

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
`<slug>.<type>.md` where type is `feature`, `fix` or `change`. Write it as a release note
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
