`keelline init` now renders the CI workflow from `[ci] ref` in `keelline.toml` rather than from
the release it resolved, so the ref the workflow pins and the ref the configuration records are
always the same value. On a repository that already carried a `keelline.toml` — which `init`
reads as your answers and does not rewrite — the workflow pins the ref that file records, and a
repository recording none gets no workflow until you write one or `keelline upgrade` does. Before this, an adopted configuration could be left pinning one commit in
`.github/workflows/keelline.yml` and recording another in `keelline.toml`, which `keelline
doctor` correctly reports red on the very next run. `[ci] ref` is also held to a full-length
commit sha before it is written into the workflow, the way `[ci] gate_branch` is held to a plain
branch name.
