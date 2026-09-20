# tests/guards/test_surface.py
"""What this area publishes. The three checks every surface is held to are
`tests/test_surfaces.py`'s; this list is the one thing that is this area's own."""

from __future__ import annotations

import keelline.guards.api as guards


def test_the_surface_carries_what_every_downstream_lane_reaches_for() -> None:
    # This list is the contract. A lane that needs something absent from it grows the list
    # deliberately, in a commit that says which lane and why — and an EQUALITY is what makes
    # that true. `required <= set(__all__)` let an export be added and pass, and so did the
    # parse that compares `__all__` against this module's own imports: adding an import and an
    # `__all__` entry together satisfied both, so between them the two could only catch a
    # REMOVED export.
    #
    # No `mutations.toml` entry: the mutation is adding an export, which is two lines in
    # `api.py` (the import and the `__all__` entry) and not one substituted line. Measured by
    # hand instead — re-exporting `hygiene.is_pytest_run` reddens this test and this test alone,
    # and under the old `required <= set(...)` the very same change left all three tests green.
    #
    # Twenty-nine names left in the wave-4 surface remediation, every one of them published
    # against `assess` — a lane `docs/cli.md` says in as many words has not shipped. What is
    # below is the whole of what another area actually imports.
    required = {
        # the git hook, for setup, and the two results its verbs return
        "HOOK_NAME",
        "HOOK_MARKER",
        "Installed",
        "Removed",
        "install",
        "uninstall",
        # where an overlay's hooks really live, for attach and doctor
        "hooks_dir",
        # which roots a configuration's paths may reach, for ledger.scan and memory.refs
        "contained_roots",
    }
    assert required == set(guards.__all__)
