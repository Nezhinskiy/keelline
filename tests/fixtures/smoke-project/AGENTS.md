# Smoke

A fixture project. Every gate the reusable workflow runs passes on it, which is what makes a
red gate in the smoke workflow a statement about Keelline rather than about this directory.

## Current status

Nothing is being built here. The roadmap is [docs/roadmap.md](docs/roadmap.md), the bug ledger
is [docs/bug-reports.md](docs/bug-reports.md), and the one entry in it is BR-001.
<!-- keelline:harness:begin -->
## Keelline

This repository is initialised with Keelline. `keelline.toml` names its document paths and
its note store. `docs/bug-reports.md` is a generated index over `docs/bugs/` — never edit it by hand;
`keelline bugs index` renders it. `docs/roadmap.md` carries the design-and-plan trail between its
markers, which `keelline docs trail` rewrites; specs live under `docs/specs/` and plans under
`docs/plans/`. Each gate runs advisory until it enforces: `keelline adopt promote` enforces the
gates that pass, and `keelline assess` says which would.
<!-- keelline:harness:end -->
