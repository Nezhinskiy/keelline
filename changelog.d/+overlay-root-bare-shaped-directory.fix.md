`keelline setup --overlay <path>` no longer records an overlay root that a repository staged inside
one of its own sibling worktrees. The check that an overlay root lies outside every checkout of the
project asked `git` where the repository was from inside the candidate directory, and `git` reads
any directory holding `HEAD`, `objects/` and `refs/` as a bare repository of its own — three paths
a repository can commit. A clone that committed such a directory beside the overlay's two manifests
made its copy in `git worktree add ../<project>.wt/<branch>` answer for itself, and it was accepted
as the machine's trust anchor while the worktree around it was refused.

`setup` now asks `git` only from the project's side, for the list of the repository's checkouts
(`git worktree list`, with implicit bare repositories refused), and refuses a candidate inside,
holding or equal to any of them. A `git` that says the project is a repository and then cannot list
its checkouts is a refusal rather than a pass, and so is a project root that sits inside a
directory `git` reads as a bare repository only by its shape. An overlay that is a repository of its
own elsewhere on disk is recorded as before.
