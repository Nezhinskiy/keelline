"""What this area publishes. The three checks every surface is held to are
`tests/test_surfaces.py`'s; this list is the one thing that is this area's own."""

from __future__ import annotations

import keelline.memory.api as memory


def test_the_c3_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # This list is the contract. A lane that needs something absent from it grows the list
    # deliberately, in a commit that says which lane and why — it does not import a private
    # module, and it does not get told after the fact that its import was a review finding.
    #
    # **An equality now, and it was a subset.** The old comment said why: ten names were on
    # `__all__` and had never been justified here, and "adding ten justifications for exports
    # this plan did not ship would be this list claiming a review it never had". That is the
    # honest form of a list nobody had audited — and it is also what let the surface reach
    # seventy names, forty-five of them with no importer anywhere. The wave-4 surface trim is
    # that review: every name below now has its argument, in `api.py` or beside it here, so the
    # assertion can be the one every other area is held to. A subset lets an export arrive
    # unnoticed, which is the hole `tests/guards/test_surface.py` names.
    #
    # No `mutations.toml` entry, for the reason every other area's surface test gives: the
    # mutation is adding an export, which is two lines in `api.py` — the import and the
    # `__all__` entry — and not one substituted line. Measured by hand instead: re-exporting
    # `store.refusal_reason` reddens this test and this test alone, and under the old
    # `required <= set(...)` it reddened nothing at all.
    required = {
        # the resolver and the store it yields, for attach, doctor and docs
        "resolve",
        "Store",
        "overlay_root",
        "permitted_roots",
        "main_checkout",
        # the overlay's per-project layout: attach writes it, overlay renders it
        "PROJECTS",
        "PROJECT_RECORD",
        "COMMON_GROUP",
        # the link tree attach builds and doctor reports on
        "link",
        "attach_main",
        "detach_main",
        "harness_anchor",
        "harness_link_needed",
        "harness_memory_path",
        "Links",  # what `link` returns
        "PartialLink",  # what it raises part-way, carrying `.created`
        # the bundles doctor reports on, and the two types they are made of
        "fit",
        "render",
        "SLOTS",
        "Bundle",
        "Fit",
        # the wiki-link grammar and the note walk the graph check reads
        "WIKI_LINK",
        "walk",
        "Walk",  # what `walk` returns
        "Note",  # what a `Walk` carries
        "Provenance",  # what a `Note` carries
        # the binding's git answer: "git said no" told from "git could not be asked"
        "origin_remote",
        "GitUnavailable",
        # the trust region, whole. Reading one needs `markers` and `DELIMITER`, which
        # tests/test_install_path.py already imports; producing one needs `wrap` and a nonce,
        # and a forged marker raises `UnsafeNote`. Half a closed vocabulary cannot be used by
        # the consumer handed a value from it.
        "markers",
        "DELIMITER",
        "wrap",
        "new_nonce",
        "UnsafeNote",
        # the trust gate. Repository bytes reach a model only after `keelline memory trust`
        # and only inside a delimited region, so a lane that injects them has to be able to
        # ask this area whether it may, to see a store that was trusted and is not any more,
        # and to tell a broken record from an unapproved store.
        "may_inject",
        "changed",
        "TrustState",
        "UnreadableTrustRecord",
    }
    assert required == set(memory.__all__)
