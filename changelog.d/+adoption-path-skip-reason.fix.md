`keelline init` now tells an adopted repository the truth about why it got no CI workflow. With a
hand-written `keelline.toml` that records no `[ci] ref` — the ordinary adoption path, under the
preset's `[ci] mode = "reusable"` — the skip reason used to be about the network: "the public
repository could not be asked for its tags ... run `keelline init --yes` again with the network
reachable", or "no released Keelline tag matches the version running". Neither was the reason,
and running again could never produce a workflow: `keelline.toml` is a create-once artifact
already on disk, so no pin any run resolves is ever recorded.

The reason is that the document records no ref, and that is what the run now says, whatever the
public repository answered. The remedy says which run can still act on it: write a released
commit into `[ci] ref` before the repository is initialised and `init` renders the workflow
around it; on one already initialised, `init` refuses to run again, so the workflow is yours to
write or `keelline upgrade` (ships later) writes it. That path no longer asks the public
repository for its tags at all, since nothing it could answer changes the outcome — which was up
to five minutes of waiting offline.

The same dead remedy is gone from a fresh repository too. With the network down, a run that
writes used to print "run `keelline init --yes` again with the network reachable", and the next
run refused because the first had initialised the repository. Only a `--dry-run` is offered that
remedy now; a run that wrote says to record a released commit in `[ci] ref` and write the
workflow by hand, or to wait for `keelline upgrade`.
