# Releasing Keelline

Version discipline itself is enforced — `keelline release check` cross-checks six sources and
runs in CI. What was undocumented is everything around it: how to cut a release at all. This
file is that, so the bus factor of the release process is not one.

## The six sources

`uv run keelline release check` refuses unless these agree:

| Source | Where the version lives |
|---|---|
| `pyproject.toml` | `project.version` |
| `uv.lock` | the `keelline` package entry — stale unless `uv sync` has run |
| `src/keelline/__init__.py` | `__version__` |
| `.claude-plugin/plugin.json` | `version` |
| `.codex-plugin/plugin.json` | `version` |
| `CHANGELOG.md` | the first `## <version>` heading after the towncrier marker |

`.claude-plugin/marketplace.json` carries no version of its own and is checked for consistency
rather than for a number.

**One version this file does not check, and somebody has to.** `.github/workflows/ci.yml` and
`.github/workflows/smoke.yml` each `npm install -g @anthropic-ai/claude-code@<version>` — the
validator the first one runs and the installer the second one runs are the same tool, and the
two pins must move together. A global npm install is not a manifest, so Dependabot does not see
either of them: bump both by hand, in one commit, and let the smoke run say whether an install
still works.

## Cutting a release

1. **Be on `main`, current, and green.** The release workflow builds from the tag, so anything
   not merged is not in the release.

   ```bash
   git switch main && git pull
   uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy
   ```

2. **Build the changelog.** Towncrier consumes `changelog.d/` and writes the section:

   ```bash
   uv run towncrier build --version X.Y.Z
   ```

   Read what it wrote. A fragment written as a note to the author rather than as a release note
   is worth fixing now — this is the text users see.

3. **Set the version in the five other places.** `pyproject.toml`, `src/keelline/__init__.py`,
   both plugin manifests, and then `uv sync` so `uv.lock` follows.

   ```bash
   uv sync
   uv run keelline release check     # must print "one version everywhere: X.Y.Z"
   ```

4. **Commit and tag.** Two tags, deliberately: `claude plugin tag` creates
   `<name>--v<version>`, which is the shape the marketplace reads, while `vX.Y.Z` is the shape
   everything else expects. The release workflow triggers on `v*`.

   ```bash
   git commit -am "chore(release): X.Y.Z"
   git tag vX.Y.Z
   git tag keelline--vX.Y.Z
   git push origin main --tags
   ```

5. **Watch the release workflow.** It rebuilds, re-runs `release check` against the tag, and
   publishes to PyPI through Trusted Publishing. Nothing is uploaded from a laptop, and no API
   token exists to leak.

## Trusted Publishing, once

The workflow authenticates to PyPI with a short-lived OIDC token rather than a stored secret,
which requires a one-time registration on PyPI:

**PyPI → Your projects → keelline → Publishing → Add a new publisher (GitHub)**

| Field | Value |
|---|---|
| Owner | `Nezhinskiy` |
| Repository | `keelline` |
| Workflow | `release.yml` |
| Environment | `pypi` |

For the very first release, before the project exists on PyPI, use PyPI's **pending publisher**
form instead — same fields, reached from your account's publishing settings.

Then create the `pypi` environment in **GitHub → Settings → Environments**, and add yourself as
a required reviewer. That is the last human gate: a tag pushed by mistake waits for an approval
instead of becoming a permanent PyPI release. PyPI does not allow re-uploading a version.

## Before the first public release

Two gates that are not automated, because they are judgement rather than a check:

- **`README.md`** is also the PyPI long description. It currently hands users an install
  command for a tool that rewrites their filesystem. It must say what Keelline does, what it
  writes, and that it is POSIX-only, before it is the first thing a stranger reads.
- **End-user documentation.** `keelline memory` has eight subcommands documented by one-line
  `help=` strings. A user cannot currently learn what `memory trust` trusts, or what `apply`
  will write into their repository, without reading the source.

## If something goes wrong

- **The tag is wrong and nothing published.** Delete both tags locally and on the remote, fix,
  re-tag.
- **PyPI published a bad release.** You cannot replace it. Yank it on PyPI (which hides it from
  resolvers without breaking anyone who has already pinned it) and release a patch version.
- **`release check` fails in the workflow but passed locally.** Almost always `uv.lock`: `uv
  sync` was not run after the version bump, so the lockfile still carries the old one.
