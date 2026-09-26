`keelline init --yes` takes the base branch from `origin/HEAD` only when it names a plain branch
under `refs/remotes/origin/`; any other name the remote reported is replaced by `main` rather than
written into `keelline.toml`, and the report says so in a `note:` line without repeating the name.
A tag or a local branch called `origin/<branch>` no longer turns the base branch into
`remotes/origin/<branch>`. With no `origin` remote at all, the branch checked out is the base
branch, with a `note:` when it is not `main`. A repository created locally and pushed has an
`origin` and no `origin/HEAD`: there the base branch stays `main`, never the feature branch you
may be adopting from, and the `note:` names `git remote set-head origin --auto` and
`--base-branch`.
