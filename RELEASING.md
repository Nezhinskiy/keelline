# Releasing Keelline

Version discipline itself is enforced — `keelline release check` cross-checks six sources, a
tag and the record of the shipped files, and runs in CI. What was undocumented is everything
around it: how to cut a release at all. This file is that, so the bus factor of the release
process is not one.

The sequence, once, before the detail: `release check` → `claude plugin tag` → towncrier
assembles `CHANGELOG.md` from the `changelog.d/` fragments → the `vX.Y.Z` tag → the GitHub
Release, attached to `vX.Y.Z` only and never to the floating `v1`, which immutable releases
would freeze → `keelline overlay publish-template`, which renders `templates/overlay/` and
pushes it to the template repository from your own authenticated checkout, so the public
repository's CI holds no credential that can write a second repository → the `v1` alias moves.

## 1. The sources

`uv run keelline release check` refuses unless these agree:

| Source | Where the version lives |
|---|---|
| `pyproject.toml` | `project.version` |
| `uv.lock` | the `keelline` package entry — stale unless `uv sync` has run |
| `src/keelline/__init__.py` | `__version__` |
| `.claude-plugin/plugin.json` | `version` |
| `.codex-plugin/plugin.json` | `version` |
| `CHANGELOG.md` | the first `## <version>` heading after the towncrier marker |
| `hooks/hashes.json` | **not a version.** The record of the three files the harness runs — `hooks/run-hook.sh`, `hooks/hooks.json` and `scripts/keelline`. `release check` fails while it is stale and `keelline release hashes` refreshes it, in whichever commit changed one of them. Nothing touches it at release time. |

`.claude-plugin/marketplace.json` carries no version of its own and is checked for consistency
rather than for a number.

`keelline release check --tag vX.Y.Z` adds the tag as a further source and tightens one rule: a
fragment still pending in `changelog.d/` is a finding rather than a licence for `CHANGELOG.md`
to lag. That is the form `release.yml` runs.

## 2. Cutting a release

**If this is the first release, do §3 first.** The `pypi` environment is the only human
gate this process has, and it is a gate only once it exists: GitHub **auto-creates** an
environment that a job names and the repository does not have, with no protection rules on it.
So a first release run top to bottom without §3 waits for nobody — `publish` runs unapproved
and fails on Trusted Publishing for want of a pending publisher, and `github-release` runs
unapproved and creates a public GitHub Release. §3 is what makes step 7's sentence true.

1. **Be on `main`, current, and green.** The release workflow builds from the tag, so anything
   not merged is not in the release.

   ```bash
   git switch main && git pull
   uv run pytest --cov --cov-report=term-missing --cov-fail-under=92
   uv run ruff check . && uv run ruff format --check . && uv run mypy
   uv run keelline release check
   claude plugin validate --strict .claude-plugin/plugin.json
   claude plugin validate --strict .claude-plugin/marketplace.json
   claude plugin validate .codex-plugin/plugin.json
   claude plugin tag --dry-run .
   ```

2. **Decide the version.** This is a judgement, not a command: the design names `v1.0.0` for
   the first public release and the tree currently says `0.1.0` and "Development Status :: 3 -
   Alpha". Every mechanism in this file works with whatever number you pick — the gate compares
   the tag to the sources rather than to a number it knows, and the alias is the major.

3. **Set it in the four places you edit by hand**, then let the lockfile follow:
   `pyproject.toml`, `src/keelline/__init__.py`, and both plugin manifests.

   ```bash
   uv sync
   uv run keelline release check   # names every source that still disagrees
   ```

   That is four of the six sources; `uv.lock` is the fifth and `uv sync` above writes it.
   `CHANGELOG.md` is the sixth and is still behind here; a pending fragment is what lets it
   lag, and step 4 catches it up.

   **And the two example configurations, which are on no gate at all.** `README.md`'s and
   `docs/cli.md`'s example `keelline.toml` blocks both carry `version = "0.1.0"`; after the
   first release that is a copy-paste that makes `keelline doctor` warn on a brand-new
   project. `release check` cannot see them — they are examples and not sources — so they
   are named here or nowhere.

4. **Assemble the changelog.**

   ```bash
   uv run keelline release notes --version X.Y.Z --draft   # read it first; writes nothing
   uv run keelline release notes --version X.Y.Z
   uv run keelline release check                           # must print "one version everywhere: X.Y.Z"
   ```

   Read what it wrote, and **edit it**. A fragment written as a note to the author rather than
   as a release note is worth fixing now — this is the text users see. The version comes before
   the changelog because `release notes` refuses a `--version` that is not the project's; after
   this step `CHANGELOG.md` carries the heading and `changelog.d/` is empty.

   **On a first release, fold the `Fixed` entries into the features they repair.** There is no
   released version for a fix to be a fix *relative to*, so every `Fixed` entry in 0.1.0
   describes a bug no user could have met — and reads as a warning about the release it ships
   in. `init`, `attach`, `doctor` and the overlay lane each accumulated several of these while
   the wave was open, which is correct while it is open: the fragments are the per-commit
   record, and a fold done earlier is undone by the next commit. Do it here, once, over the
   assembled file: state the feature as what it now is, delete the fixes that only describe
   its development, and keep the ones a reader of 0.1.0 has to act on — a grammar that refuses
   a `keelline.toml` which loaded before, a flag that means something narrower than it sounds.
   The same folding applies to a `Changed` entry that changed something never released.
   `release check --tag` cannot judge this: it counts pending fragments and never reads them.

5. **Edit the README's install section, then commit.** In `README.md`, replace everything
   between `<!-- release-install:begin -->` and `<!-- release-install:end -->` — the markers,
   included — with the text in the HTML comment directly above them, which carries the two
   tagged install forms. **The whole marked region, not only the "Nothing is released yet."
   paragraph**: the replacement brings its own code blocks, so a partial swap would leave the
   untagged install commands standing beneath the tagged ones and keep a "From the first
   release on…" promise that the release just falsified. It is written in the comment so this
   is an edit and not a composition. Do it now: the commit below is the release commit, and
   after step 6 the tag points at whatever this commit contains.

   ```bash
   git commit -am "chore(release): X.Y.Z"
   ```

6. **Tag, twice, and check the tag.** `claude plugin tag` creates `keelline--vX.Y.Z`, the
   per-plugin shape the plugin tooling writes so a marketplace can resolve *this plugin's*
   version independently of the repository's; `vX.Y.Z` is the shape everything else expects
   and the one `release.yml` triggers on. Both name the same commit, which is why
   `README.md`'s install paragraph can hand a reader `…@vX.Y.Z` — `/plugin marketplace add`
   takes any git ref — while the `keelline--` tag is the one the tooling itself looks for.
   Neither is a substitute for the other; make both.

   **No prerelease tags.** `release check --tag` compares the tag to `pyproject.toml`'s
   literal version string, and `uv.lock` normalises a PEP 440 prerelease (`0.1.0-rc1` becomes
   `0.1.0rc1`), so the six-source rule cannot be satisfied by an `rc` today. `release.yml`
   triggers on finals only, deliberately.

   ```bash
   claude plugin tag .
   git tag vX.Y.Z
   uv run keelline release check --tag vX.Y.Z
   git push origin main --tags
   ```

7. **Watch the workflow.**

   ```bash
   gh run list --workflow release --limit 1
   gh run watch <id> --exit-status
   ```

   `build` runs the gate against the tag, tests, builds and attests. **Once §3's `pypi`
   environment exists with a required reviewer**, `publish` waits for its approval, and
   `github-release` waits for the same environment and does not depend on `publish`, so a
   declined PyPI still leaves you a Release. Without that environment both jobs run straight
   through the name GitHub invents for them, and nothing on this tag waits for a human.

8. **Publish the overlay template**, from this checkout, with an authenticated `gh` and an SSH
   key GitHub knows:

   ```bash
   uv run keelline overlay publish-template --owner Nezhinskiy        # read the plan
   uv run keelline overlay publish-template --owner Nezhinskiy --yes  # do it
   ```

   Without `--yes` nothing outward-facing happens: it renders, asks `gh` what is there, and
   reports what it would create, mark and push.

9. **Move the alias** — for a `1.x` release; the alias is the major.

   ```bash
   git tag -f v1 vX.Y.Z && git push -f origin v1
   ```

10. **Run the cross-repository smoke at the alias.**

    ```bash
    gh workflow run smoke-release.yml
    gh run watch <id> --exit-status
    ```

## 3. One-time setup

**Trusted Publishing.** The workflow authenticates to PyPI with a short-lived OIDC token rather
than a stored secret, which requires a one-time registration on PyPI:

**PyPI → Your projects → keelline → Publishing → Add a new publisher (GitHub)**

| Field | Value |
|---|---|
| Owner | `Nezhinskiy` |
| Repository | `keelline` |
| Workflow | `release.yml` |
| Environment | `pypi` |

For the very first release, before the project exists on PyPI, use PyPI's **pending publisher**
form instead — same fields, reached from your account's publishing settings.

**The `pypi` environment — before the first tag, not after it.** Create it in **GitHub →
Settings → Environments**, and add yourself as a required reviewer. That is the last human
gate, and both `publish` and `github-release` wait behind it: a tag pushed by mistake waits
for an approval instead of becoming a permanent PyPI release or a public GitHub Release.
PyPI does not allow re-uploading a version. **Create it first**: naming an environment that
does not exist does not fail the job — GitHub creates one on the spot, with no protection
rules — so a release cut before this step would have the gate's two `environment:` lines and
none of the gate.

This paragraph is no longer the whole of the defence. `release.yml`'s `environment-gate` job
reads the environment's protection-rule count over the API before either gated job can start,
and fails the run when it is zero: the order these two sections are written in is now checked
rather than asked for. If the workflow's own token cannot read
`GET /repos/OWNER/REPO/environments/NAME` — the endpoint is not open to every default token —
the gate refuses by default, and the way to say "it is a real gate, the read is simply closed
to me" is a repository variable, **Settings → Secrets and variables → Actions → Variables**,
`PYPI_ENVIRONMENT_PROTECTED = true`. It stands in for the *read* only: an environment that
reads back with zero rules fails whatever the variable says. Set it only after the environment
and its reviewer exist.

**Tag protection.** A repository ruleset over `refs/tags/v*.*.*` and `refs/tags/keelline--v*`
with `deletion` and `update` rules, so a semver tag is immutable while the `v1` alias — which
matches neither pattern — can still move:

```bash
gh api -X POST repos/Nezhinskiy/keelline/rulesets --input - <<'JSON'
{"name": "release tags", "target": "tag", "enforcement": "active",
 "conditions": {"ref_name": {"include": ["refs/tags/v*.*.*", "refs/tags/keelline--v*"], "exclude": []}},
 "rules": [{"type": "deletion"}, {"type": "update"}]}
JSON
```

**A conduct contact address.** `CODE_OF_CONDUCT.md` still routes a report through the security
advisory form. That is worth a real address before the repository is advertised.

## 4. The harness CLI version

`.github/workflows/ci.yml` and `.github/workflows/smoke.yml` each `npm install -g
@anthropic-ai/claude-code@<version>` — the validator the first one runs and the installer the
second one runs are the same tool, and the two pins must move together. A global npm install is
not a manifest, so Dependabot does not see either of them: bump both by hand, in one commit,
and let the smoke run say whether an install still works.

**The overlay template's own action pins.** `src/keelline/templates/overlay/.github/workflows/scan.yml`
pins two actions by full-length sha, and this repository's `.github/dependabot.yml` scans
`.github/workflows/` at the root and nothing else — a nested tree under `src/` is not a
workflow directory the platform reads, so those two pins rot here until somebody looks.
A rendered overlay ships its own `dependabot.yml` and keeps itself current from then on;
what this line is about is the state every *new* overlay starts from. Check them here, at
the release that publishes the template.

**The project workflow's pin, and what the first tag unlocks.** There is a second sha-pinned
template now: `src/keelline/templates/project/keelline.yml`, the caller `keelline init` renders
into an adopting project's `.github/workflows/`. Its `uses:` line is not pinned in the tree —
the sha is filled in at render time, and it is the commit of the *released* Keelline that did
the rendering, read off this repository's own `v*` tags. So nothing here rots, and nothing here
needs checking at a release; what a release changes is whether the workflow can be written at
all. Before the first tag `init` finds no released commit to name, reports the workflow skipped
with that reason, and writes nothing into `.github/` — which means every project initialised
before the first release carries no CI caller and no `[ci] ref`, and gets both when `keelline
upgrade` ships. The first tag is the event that changes that, and it changes it for new
projects only.

## 5. If something goes wrong

- **The tag is wrong and nothing published.** Delete both tags locally and on the remote, fix,
  re-tag. A tag the ruleset refuses to delete or move is a tag that was already released: pick
  the next patch version instead.
- **PyPI published a bad release.** You cannot replace it. Yank it on PyPI (which hides it from
  resolvers without breaking anyone who has already pinned it) and release a patch version.
- **`release check` fails in the workflow but passed locally.** Almost always `uv.lock`: `uv
  sync` was not run after the version bump, so the lockfile still carries the old one. The
  other candidate is `hooks/hashes.json`, if a shipped file moved without `keelline release
  hashes`.
- **`publish-template` pushed the wrong tree.** The next `publish-template` fixes it: it
  replaces the tree whole rather than merging into it.
