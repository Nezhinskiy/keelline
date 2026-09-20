from __future__ import annotations

import keelline.memory.api as memory


def test_the_c3_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # This list is the contract. A lane that needs something absent from it grows the list
    # deliberately, in a commit that says which lane and why — it does not import a private
    # module, and it does not get told after the fact that its import was a review finding.
    required = {
        "Bundle",
        "DELIMITER",
        "Fit",
        "IndexCheck",
        "Note",
        "NoteError",
        "NoteType",
        # `link` raises this and it carries `.created`; `attach` binds and links.
        "PartialLink",
        # And `link` *returns* this. It was `list[Path]` until the harness link learned to be
        # withdrawn, and the commit that changed the signature changed neither this list nor
        # `api.py` — which is what the derived test below now catches without being told.
        "Links",
        "Provenance",
        "Reconciliation",
        "SLOTS",
        "Store",
        "UnsafeNote",
        "Walk",
        "blocks",
        "check_index",
        "fit",
        # `inside_project` sends the reader to `in_repository` by name, `worktree` and
        # `bundles` both send them to `index_source`, and `attach` is the lane that creates
        # the symlinked index those two rules govern.
        "in_repository",
        "index_source",
        "INDEX_NAME",
        "inventory",
        "link",
        "linked_names",
        "markers",
        "may_inject",
        "new_nonce",
        "permitted_roots",
        "read_note",
        "reconcile",
        # `write_note` is on this list and `store_digest` covers every note, so a lane that
        # rewrites one in a trusted store revokes the record it depends on unless it can do
        # the same dance `memory index` does.
        "refresh_if_trusted",
        "Snapshot",
        "snapshot",
        "refusal_reason",
        "render",
        "render_index",
        "render_note",
        "resolve",
        "totals",
        "walk",
        "with_index",
        "wrap",
        "write_index",
        # memory refs (the wave-2 closure plan's Task 11); docs-tooling and the
        # memory-sweep skill read it
        "WIKI_LINK",
        "RefsReport",
        "unresolved",
        "audience_violations",
        "check_refs",
    }
    # A subset and not an equality: ten names this lane exported before the wave-2 closure
    # plan — `Entry`, `TrustState`, `UnreadableTrustRecord`, `changed`, `inside_project`,
    # `main_checkout`, `overlay_root`, `resolved`, `split`, `write_note` — are on `__all__`
    # and were never added here, and adding ten justifications for exports this plan did not
    # ship would be this list claiming a review it never had. The derived test below is what
    # catches a name nobody added to either side.
    assert required <= set(memory.__all__)
