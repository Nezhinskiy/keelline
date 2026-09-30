A newly created overlay's secret scan now starts from current releases: its `scan` workflow pins
`actions/checkout` v7.0.1 and `gitleaks/gitleaks-action` v3.0.0, both of which declare the Node 24
runtime, and its pre-commit hook pins gitleaks v8.30.1 where it pinned v8.21.2. The workflow still
fetches the full history and scans the commits each push or pull request adds, and needs no licence
key for an overlay on a personal account. The action still runs its own gitleaks binary (8.24.3
unless `GITLEAKS_VERSION` says otherwise), so the workflow and the hook do not scan with the same
gitleaks version. In an overlay you already created, `stayfixed overlay upgrade` brings an untouched
`.github/workflows/scan.yml` and `.pre-commit-config.yaml` along; a file you or Dependabot have
edited is left alone and named, and the overlay's own Dependabot configuration keeps the workflow's
pins current either way.
