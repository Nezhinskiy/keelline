The `plan` gate and `keelline plan check` now lint every plan that merging the change could alter
on the base: one whose copy in `HEAD` differs from the base's and from that of any commit
`git merge-base --all <base> HEAD` names, not only the one `<base>...HEAD` diffs against. A
history the change shapes itself can have several merge bases, and the one git picks alone can
already hold an old plan the change puts back: that change was linted clean, and merging it put
the plan back on the base. A shallow clone is now `base-unresolvable` like a base that does not
resolve, because the merge base git sees there can be an older commit that holds the old plan
too; and when git cannot say whether the clone is shallow, the gate fails rather than assuming a
full one.

`keelline test attribute` no longer picks one merge base when `HEAD` and the base have several, or
when the clone is shallow. Each of several is as much "before this change" as the others, and the
one git picks alone could file a failure the change brought back as pre-existing. The command now
says the attribution is undetermined, counts the merge bases, names up to eight of them and the
remedy, and runs nothing.

`plan`, `bugs` and `test attribute` now ask git for the merge bases one way. A git a signal ended
is read as no answer everywhere; `plan` used to read it as a base that does not resolve and send
the reader to a deeper checkout.
