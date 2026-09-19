Five commands stopped reporting on questions they could not ask.

`keelline overlay publish-template --yes` used to print `<slug> already carries this Keelline's
template; nothing to push` and exit 0 whenever `git` was absent, hung, blocked by another
process's `index.lock`, or failed by a repository hook — four causes, one message, none of them
named, and the operator told the published template was current when nothing had been examined.
The `git` calls now have the guard the `gh` calls always had, and an empty `git status` listing
is read as "nothing changed" only when `git status` actually answered.

`overlay publish-template`'s dry run no longer reads every `gh repo view` failure as "the
repository does not exist". An unauthenticated `gh`, a rate limit and a network failure now
name themselves instead of producing an offer to create a repository that exists and is
private. A private repository your token may not see is the one case that cannot be told apart,
because GitHub answers 404 for it on purpose.

`keelline release check --tag` says which tags it compared against rather than inventing a
version out of the one it was given. `--tag 1.2.3` used to report `tag 1.2.3 names 1.2.3;
pyproject.toml says '1.2.3'` — two identical strings asserted to disagree — and `--tag
dev-v1.2.3` reported `names -v1.2.3`.

A `hooks/hashes.json` that is present but carries non-UTF-8 bytes, or that this process cannot
read, is now the finding it always should have been (`1`) rather than
`keelline: internal error`, exit `2`. Through `keelline doctor` that internal error carried the
remedy "report this, with the command you ran", which asked the owner to file a bug against
Keelline for a corrupt file in their own installation.

`keelline test attribute` gives its tracked-file listing the same wide bound its archive has.
On the narrow one, a large repository or a slow volume timed the listing out, and the guard that
catches a `.gitattributes` export rule was skipped silently — leaving the verdict to be computed
from an incomplete tree.
