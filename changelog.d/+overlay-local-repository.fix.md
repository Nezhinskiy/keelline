`stayfixed overlay create --local` now leaves a git repository on branch `main` with no remote,
and its last line names the two commands that give it one (`git remote add origin <url>` and
`git push -u origin main`). It used to leave a plain directory. A directory that is already a git
repository is left on its own branch with its own remotes, and the line says so.
