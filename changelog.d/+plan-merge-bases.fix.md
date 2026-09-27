The `plan` gate and `keelline plan check` now lint every plan that differs from the base and
from any commit `git merge-base --all <base> HEAD` names, not only from the one `<base>...HEAD`
diffs against. A history the change shapes itself can have several merge bases, and the one git
picks alone can already hold an old plan the change puts back: that change was linted clean, and
merging it put the plan back on the base. A shallow clone is now `base-unresolvable` like a base
that does not resolve, because the merge base git sees there can be an older commit that holds
the old plan too, and a clone git will not say is not shallow fails rather than being read as a
full one.

`keelline test attribute` no longer picks one merge-base when `HEAD` and the base have several,
or when the clone is shallow. Each of several is as much "before this change" as the others, and
the one git picks alone could file a failure the change brought back as pre-existing. The command
now says the attribution is undetermined, names every merge-base and the remedy, and runs nothing.
