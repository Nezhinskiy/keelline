"""The scaffold engine (contract C2): manifest, regions, keyed entries, plan and apply.

Everything a consumer lane needs is re-exported here, including the four primitives the later
lanes reach for directly: `owned_ids` for `doctor`'s provenance list, `mark` for any lane that
builds `Template.entries`, and `drop` / `apply_entries` for `uninstall`. The three refusals a
consumer has to catch by name are here too: a lane that cannot import `ManifestError`,
`RegionError` or `EntriesError` from this list has no way to tell a bad merge from a bug except
by catching `Refusal` whole. `effective_target` and `unlinks` are for `uninstall`, which must
compare paths the way the engine resolves them (an `[artifacts] local` artifact lives where
`Template.target` does not say) and must know which planned removal deletes a file rather than
rewriting it without Keelline's part: both are the engine's facts, and a second copy of either
would drift from it. `matches_render` is for `uninstall` too: before any write it predicts
whether the write-once pass will remove what a region's removal leaves in a file kept out of
git, and that verdict is the engine's own rule for such a file. Importing a private module of
this package from another area is a review finding; if a lane needs something this list does
not carry, the list grows deliberately.
"""

from keelline.scaffold.engine import (
    LOCAL_ROOT,
    apply,
    effective_target,
    matches_render,
    plan,
    shipped_profiles,
    unlinks,
    validate_sources,
)
from keelline.scaffold.entries import (
    EntriesError,
    apply_entries,
    mark,
    marker_id,
    owned,
    owned_ids,
)
from keelline.scaffold.manifest import (
    FORMAT,
    MANIFEST_PATH,
    Kind,
    Location,
    Manifest,
    ManifestError,
    Record,
    digest,
)
from keelline.scaffold.model import Action, Applied, Plan, Refused, Template, Verb
from keelline.scaffold.regions import RegionError, Style, drop, extract, upsert
from keelline.scaffold.report import printable, render_report

__all__ = [
    "FORMAT",
    "LOCAL_ROOT",
    "MANIFEST_PATH",
    "Action",
    "Applied",
    "EntriesError",
    "Kind",
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
    "mark",
    "marker_id",
    "matches_render",
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
