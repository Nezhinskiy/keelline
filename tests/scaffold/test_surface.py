"""What `keelline.scaffold` publishes, which is the whole of contract C2 for a consumer."""

from __future__ import annotations

from keelline import scaffold
from keelline.errors import Refusal
from keelline.scaffold import EntriesError, ManifestError, RegionError

EXPORTED = [
    "FORMAT",
    "LOCAL_ARTIFACTS",
    "LOCAL_DIGESTS",
    "LOCAL_ROOT",
    "MANIFEST_PATH",
    "Action",
    "Applied",
    "EntriesError",
    "Kind",
    "LocalDigests",
    "Location",
    "Manifest",
    "ManifestError",
    "Plan",
    "Record",
    "Refused",
    "RegionError",
    "Style",
    "Template",
    "Verb",
    "apply",
    "apply_entries",
    "digest",
    "drop",
    "effective_target",
    "extract",
    "left_copies",
    "local_copies",
    "mark",
    "marker_id",
    "ours_locally",
    "owned",
    "owned_ids",
    "plan",
    "printable",
    "render_report",
    "shipped_profiles",
    "unlinks",
    "upsert",
    "validate_sources",
]


def test_the_three_refusals_a_consumer_catches_by_name_are_exported() -> None:
    # `Manifest.read` raises `ManifestError`, `drop` raises `RegionError`, and `owned_ids` and
    # `apply_entries` raise `EntriesError`. The package docstring makes importing a private
    # module of it from another area a review finding, so while these three were absent from the
    # list a consumer had to choose between that finding and catching `Refusal` whole — which
    # also swallows the malformed-`Template` bug the engine raises on purpose.
    for name in ("ManifestError", "RegionError", "EntriesError"):
        assert name in scaffold.__all__
    assert issubclass(ManifestError, Refusal)
    assert issubclass(RegionError, Refusal)
    assert issubclass(EntriesError, Refusal)


def test_the_published_list_is_exactly_this_and_every_name_resolves() -> None:
    # Five downstream lanes consume this surface, so the list may grow and may not shrink or
    # rename. Spelled out rather than counted, so a swap cannot pass for a no-op.
    assert scaffold.__all__ == EXPORTED
    assert [name for name in EXPORTED if not hasattr(scaffold, name)] == []
