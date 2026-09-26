`keelline setup --overlay <path>` no longer records an overlay root that a repository staged inside
one of its own sibling worktrees. The check that an overlay root lies outside every checkout of the
project asked `git` where the repository was from inside the candidate directory, and `git` reads
any directory holding `HEAD`, `objects/` and `refs/` as a bare repository of its own — three paths
a repository can commit. A clone that committed such a directory beside the overlay's two manifests
made its copy in `git worktree add ../<project>.wt/<branch>` answer for itself, and it was accepted
as the machine's trust anchor while the worktree around it was refused.

`setup` now takes the list of the repository's checkouts from the project's side
(`git worktree list`), which nothing a repository commits can change, and refuses a candidate
inside, holding or equal to any of them. It also asks `git` from the candidate upward, with implicit
bare repositories refused, for the checkouts that list names only by their git directory (a
`--separate-git-dir` repository, a submodule); that question can only add a refusal. Directories
are compared as the filesystem sees them, so a path spelled in another case on macOS is the same
checkout. A `git` that says the project is a repository and then cannot list its checkouts is a
refusal rather than a pass, and so is a project root inside a bare-shaped directory. An overlay that
is a repository of its own elsewhere on disk is recorded as before.
