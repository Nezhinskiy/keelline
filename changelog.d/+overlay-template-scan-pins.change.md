A newly created overlay's secret scan now starts from current releases: its `scan` workflow runs
`actions/checkout` v7.0.1 and `gitleaks/gitleaks-action` v3.0.0, both on the Node 24 runtime that
GitHub-hosted runners now default to (the Node 20 releases it used to pin stop running there on 16
September 2026), and its pre-commit hook pins gitleaks v8.30.1 where it pinned v8.21.2. The workflow
still grants only `contents: read`, scans the whole history on push and pull request, and needs no
licence key for an overlay on a personal account. An overlay you already created keeps the pins it
was created with; its own Dependabot configuration moves them.
