# Rename to stayfixed: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.
>
> **One implementer, one worktree.** The rename touches almost every tracked file, so nothing
> else may run in the same worktree while Task 2 is in flight, and no other branch should be cut
> from `dev` for a change that would conflict with it until this lands.

**Goal:** the unreleased project becomes `stayfixed` everywhere — package, command, plugin,
marketplace, configuration file, state directory, environment variables, tags and repository —
before the first tag, so that `0.1.0` ships under the name it keeps.

**Architecture:** a guard test states the end state first (the former name appears in no tracked
file and no tracked path outside the historical plans), then one mechanical pass applies a fixed,
ordered mapping, and the generated files (`uv.lock`, `hooks/hashes.json`) are regenerated rather
than edited. No behaviour changes; every existing test keeps its assertion and only its spelling
moves.

**Tech Stack:** Python 3.11+ standard library, `uv`, `pytest`, `ruff`, `mypy`, towncrier
fragments, the Claude Code plugin validator.

**Spec:** the rename package of wave 6 in the private extraction design, re-planned on
2026-09-28 (the name is decided there; this repository does not carry that document).

**Scope:** package `rename` of wave 6 only. A change belongs to this branch if and only if it
replaces the former name with `stayfixed`, regenerates a file the replacement invalidates, or
records the rename (changelog fragment, the plans index note). Anything else — a README rewrite,
a tagline, a behaviour fix noticed on the way — is out and waits for its own branch.

## Global Constraints

- The name is written `stayfixed`, lower case, everywhere: prose, sentence starts, headings,
  command output, URLs. The one exception is a Python class name, which keeps PEP 8 case:
  the error class becomes `StayfixedError` and the configuration section's dataclass becomes
  `Stayfixed`.
- The repository is `stayfixed/stayfixed` on GitHub. The personal account stays the author:
  `authors`, `author`, `developerName` and `CODEOWNERS` keep `Nezhinskiy`; only the marketplace
  `owner` becomes `stayfixed`.
- Runtime imports stay standard-library only; nothing in this plan adds a dependency.
- Plans under `docs/plans/` dated before 2026-09-28 are the historical record and keep the name
  they were written under. This plan is exempt as well, because it has to spell the mapping.
- The `0.1.0` version string does not change.
- No commit message contains the two characters that make a pull-request reference followed by
  a number; say "pull request" in words.

## The mapping

Applied in this order, each as a case-sensitive literal replacement, to every tracked text file
except the exemptions in Task 1. The order matters: the longer, more specific strings go first
so a later, shorter rule cannot split them.

```text
1. Nezhinskiy/keelline-overlay-template  ->  stayfixed/stayfixed-overlay-template
2. Nezhinskiy/keelline                   ->  stayfixed/stayfixed
3. KeellineError                         ->  StayfixedError
4. KEELLINE                              ->  STAYFIXED
5. Keelline                              ->  stayfixed
6. keelline                              ->  stayfixed
```

Every tracked path that carries the name moves with `git mv`, the package directory first and
then each remaining path with the name replaced in it. Outside the package that is the launcher,
three changelog fragments, the two fixture projects' configuration files, the smoke fixture's
state directory, and, inside the package, the project template's CI workflow:

```text
src/keelline/                                   ->  src/stayfixed/
scripts/keelline                                ->  scripts/stayfixed
changelog.d/+keelline-*.md (three)              ->  changelog.d/+stayfixed-*.md
tests/fixtures/*/keelline.toml (two)            ->  tests/fixtures/*/stayfixed.toml
tests/fixtures/smoke-project/.keelline/         ->  tests/fixtures/smoke-project/.stayfixed/
src/stayfixed/templates/project/keelline.yml    ->  src/stayfixed/templates/project/stayfixed.yml
```

The mapping's rule 5 also turns the configuration section's dataclass `Keelline` into a name that
collides with the local variable holding it (ruff reports `F823`); that one identifier is renamed
`Stayfixed` by hand, in its definition, its annotation, its import and its two constructor calls.
A tokenizer pass over the original tree shows `KeellineError` and `Keelline` are the only code
identifiers spelled with a capital.

**The smoke fixture's configuration moves without tripping its gate.** The `same-repository-form`
job compares the fixture's configuration with the base branch's copy byte for byte, which is why
that file may not change in a pull request. After the rename the gate reads `stayfixed.toml`, the
base has none, and a missing base copy is the bootstrap, where the change's own tree decides
(`docs/cli.md`, the `gate` section). So this change passes; the next one to touch the fixture's
configuration is held to the byte comparison again.

Measured before the rename: 9,037 lower-case, 1,070 capitalised and 143 upper-case occurrences in
471 tracked files; the upper-case ones are the seven environment variables
(`_CONFIG`, `_PYTHON_CANDIDATES`, `_DIRECTORY`, `_OLD_PYTHON`, `_STORE`, `_INVOCATIONS`,
`_GIT_FLOOR_SECONDS`), and `KeellineError` is the only capitalised identifier.

---

### Task 0: Move the repository (owner, manual)

This is the owner's step and happens before anything is pushed: the workflows this branch
rewrites call `stayfixed/stayfixed/.github/workflows/check.yml`, which has to exist when CI runs.

- [ ] **Step 1: Transfer and rename on GitHub.** Settings → General → Transfer ownership to the
  `stayfixed` organisation, then rename the repository to `stayfixed`. GitHub keeps redirects from
  the old URLs.
- [ ] **Step 2: Point every local checkout at the new remote.**

```bash
git remote set-url origin git@github.com:stayfixed/stayfixed.git
git fetch origin
```

- [ ] **Step 3: Read back what the transfer carried.** Expected: the `dev` branch protection
  still lists the nine required checks (`oracle`, `plugin`, four `checks (…)` legs, two
  `installed-plugin (…)` legs, `same-repository-form / gates`), and the `release tags` ruleset is
  present and active.

```bash
gh api repos/stayfixed/stayfixed/branches/dev/protection/required_status_checks --jq '.contexts[]'
gh api repos/stayfixed/stayfixed/rulesets --jq '.[]|"\(.name) \(.enforcement)"'
```

If either is missing, recreate it from `RELEASING.md` before Task 3's push.

### Task 1: The guard test

**Files:**
- Test: `tests/test_name.py` (create)

**Interfaces:**
- Consumes: `tests.test_neutral.ROOT`, `tests.test_neutral.tracked_files()`.
- Produces: nothing later tasks import; the test is the rename's acceptance criterion.

- [ ] **Step 1: Write the failing test**

```python
"""The project has one name, and the former one survives only in the historical plans.

The rename to stayfixed happened before the first release, so nothing a user can install ever
carried the former name, and nothing tracked should carry it now: not a module path, not an
environment variable, not a sentence. The plans written before the rename are the record of the
work as it was argued and keep their wording, and so does the plan that spells the mapping.
The former name is assembled from two halves so this file does not match itself.
"""

from __future__ import annotations

import re

from tests.test_neutral import ROOT, tracked_files

FORMER = "keel" + "line"
PATTERN = re.compile(FORMER, re.IGNORECASE)

# Plans dated before the rename, the plan that performs it, and this file.
RENAME_DAY = "2026-09-28"


def _exempt(relative: str) -> bool:
    if relative == "tests/test_name.py":
        return True
    if relative.startswith("docs/plans/") and relative != "docs/plans/README.md":
        name = relative.removeprefix("docs/plans/")
        return name[:10] < RENAME_DAY or name == f"{RENAME_DAY}-rename-stayfixed.md"
    return False


def test_no_tracked_path_carries_the_former_name() -> None:
    hits = [
        str(p.relative_to(ROOT))
        for p in tracked_files()
        if PATTERN.search(str(p.relative_to(ROOT))) and not _exempt(str(p.relative_to(ROOT)))
    ]
    assert hits == [], f"{len(hits)} path(s) still carry the former name, first: {hits[:5]}"


def test_no_tracked_file_mentions_the_former_name() -> None:
    hits: list[str] = []
    for path in tracked_files():
        relative = str(path.relative_to(ROOT))
        if _exempt(relative):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if PATTERN.search(text):
            hits.append(relative)
    assert hits == [], f"{len(hits)} file(s) still mention the former name, first: {hits[:5]}"
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_name.py -q`
Expected: FAIL, both tests, the path test naming `src/keelline/…` entries and the text test
reporting about 470 files.

- [ ] **Step 3: Commit**

```bash
git add tests/test_name.py
git commit -m "test(name): state that the former name survives only in the historical plans"
```

### Task 2: The mechanical rename

**Files:**
- Modify: every tracked text file outside the exemptions (the mapping above)
- Modify: `pyproject.toml` (package name, script entry, `extend-include`, via the mapping)
- Modify: `.claude-plugin/marketplace.json` (the `owner` name)
- Modify: `docs/plans/README.md`
- Modify: `uv.lock`, `hooks/hashes.json` (regenerated)
- Create: `changelog.d/+rename-stayfixed.change.md`

**Interfaces:**
- Consumes: the guard test from Task 1.
- Produces: the package `stayfixed` with the console script `stayfixed`, the configuration file
  `stayfixed.toml`, the state directory `.stayfixed/`, the environment variables `STAYFIXED_*`,
  the tag prefix `stayfixed--v`, the error class `stayfixed.errors.StayfixedError`.

- [ ] **Step 1: Move the paths**

```bash
git mv src/keelline src/stayfixed
git ls-files -z | python3 -c '
import sys, subprocess, pathlib
for n in sys.stdin.buffer.read().decode().split("\0"):
    if not n or "keelline" not in n.lower() or n.startswith("docs/plans/"):
        continue
    new = n.replace("keelline", "stayfixed")
    pathlib.Path(new).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "mv", n, new], check=True)
'
```

- [ ] **Step 2: Apply the mapping to every tracked text file outside the exemptions**

```bash
git ls-files -z | python3 -c '
import sys, pathlib
RULES = [
    ("Nezhinskiy/keelline-overlay-template", "stayfixed/stayfixed-overlay-template"),
    ("Nezhinskiy/keelline", "stayfixed/stayfixed"),
    ("KeellineError", "StayfixedError"),
    ("KEELLINE", "STAYFIXED"),
    ("Keelline", "stayfixed"),
    ("keelline", "stayfixed"),
]
def exempt(n):
    if n == "tests/test_name.py":
        return True
    if n.startswith("docs/plans/") and n != "docs/plans/README.md":
        name = n.removeprefix("docs/plans/")
        return name[:10] < "2026-09-28" or name == "2026-09-28-rename-stayfixed.md"
    return False
for n in sys.stdin.buffer.read().decode().split("\0"):
    if not n or exempt(n):
        continue
    p = pathlib.Path(n)
    try:
        t = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
        continue
    u = t
    for a, b in RULES:
        u = u.replace(a, b)
    if u != t:
        p.write_text(u, encoding="utf-8")
'
```

- [ ] **Step 3: Set the marketplace owner to the organisation.** In
  `.claude-plugin/marketplace.json` change `"owner": { "name": "Nezhinskiy" }` to
  `"owner": { "name": "stayfixed" }`. Leave every `author` and `developerName` as it is.

- [ ] **Step 4: Note the rename in the plans index.** Append to `docs/plans/README.md`:

```markdown
The project was renamed to stayfixed on 2026-09-28, before its first release. Plans dated
earlier were written under the former name and keep it, as the record of the work as it was
argued; their module paths and commands read `stayfixed` today.
```

- [ ] **Step 5: Record the rename for the changelog.** Create
  `changelog.d/+rename-stayfixed.change.md`:

```markdown
The project is named stayfixed: the package and the command are `stayfixed`, a repository's
configuration is `stayfixed.toml` and its state directory `.stayfixed/`, the environment
variables are `STAYFIXED_*`, release tags are `stayfixed--vX.Y.Z`, and the repository is
`stayfixed/stayfixed`.
```

- [ ] **Step 6: Regenerate the generated files**

```bash
uv lock
uv run stayfixed release hashes
```

Expected: `uv.lock` names the package `stayfixed`; `hooks/hashes.json` lists
`scripts/stayfixed` and new digests for the hook files the mapping touched.

- [ ] **Step 7: Run the guard test**

Run: `uv run pytest tests/test_name.py -q`
Expected: PASS, both tests.

- [ ] **Step 8: Lint and type-check, then fix what the longer name pushed over the line**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: the only findings are `E501` lines the one-character-longer name pushed past 100
columns and format drift from the same cause. Re-wrap those lines by hand; change no logic.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "chore: rename the project to stayfixed before its first release"
```

### Task 3: Prove the renamed tree and open the change

**Files:**
- Modify: whatever the checks below show the mapping left inconsistent (expected: nothing)

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: a pull request into `dev` on `stayfixed/stayfixed`.

- [ ] **Step 1: Run the project's own gates on the renamed tree**

These are the steps the `checks` and `plugin` jobs of `.github/workflows/ci.yml` run. The
repository carries no configuration file of its own, so its `docs check` and `plan check` are
not among them.

```bash
uv sync --locked
uv run stayfixed release check
uv build
uv run python scripts/check_artifacts.py dist
claude plugin validate .claude-plugin/plugin.json --strict
claude plugin validate .claude-plugin/marketplace.json --strict
claude plugin validate .codex-plugin/plugin.json
```

Expected: every command exits 0. A failure here is a spot the mapping could not see (for
example a width assertion on printed text that grew by one character); fix the spot, keep the
assertion's meaning, and record it in the commit message.

- [ ] **Step 2: Run the full suite through the machine-wide queue**

```bash
# HEAVY is the machine-wide queue wrapper (`heavy.sh OUTPREFIX -- cmd…`) the owner's sessions share;
# set it to its path on this machine.
HEAVY="${HEAVY:?set HEAVY to the heavy.sh queue wrapper}"
$HEAVY "${TMPDIR:-/tmp}/rename-suite" -- uv run pytest -n auto --cov --cov-fail-under=92
cat "${TMPDIR:-/tmp}/rename-suite.exit"
```

Expected: exit 0, coverage at or above 92.

- [ ] **Step 3: Run the mutation oracle through the same queue, on a committed tree**

```bash
$HEAVY "${TMPDIR:-/tmp}/rename-oracle" -- uv run python scripts/mutation_oracle.py
cat "${TMPDIR:-/tmp}/rename-oracle.exit"
```

Expected: exit 0. The warm cache misses on every renamed path, so this run is a cold one.

- [ ] **Step 4: Push and open the pull request** (after Task 0)

```bash
git push -u origin chore/rename-stayfixed
gh pr create --repo stayfixed/stayfixed --base dev --title "chore: rename the project to stayfixed" --body-file -
```

The body says what moved (the list under Interfaces of Task 2), that no behaviour changed, that
the historical plans keep the former name, and which gates ran locally with their exit codes.

- [ ] **Step 5: Read the pull request's checks before calling the task done.** Expected: the nine
  required checks green on `stayfixed/stayfixed`. A red leg is a finding to fix on this branch,
  not a reason to merge with an override.

## After this plan

The release package of wave 6 continues under the new name: the owner's one-time setup in
`RELEASING.md` (the PyPI pending publisher registered for project `stayfixed`, repository
`stayfixed/stayfixed`, workflow `release.yml`, environment `pypi`), then the tag, the template
repository `stayfixed/stayfixed-overlay-template`, the smoke and the reusable-workflow check.
