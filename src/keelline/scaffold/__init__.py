"""The scaffold engine (contract C2): manifest, regions, keyed entries, plan and apply.

Everything a consumer lane needs is re-exported here, including the four primitives the later
lanes reach for directly: `owned_ids` for `doctor`'s provenance list, `mark` for any lane that
builds `Template.entries`, and `drop` / `apply_entries` for `uninstall`. Importing a private
module of this package from another area is a review finding; if a lane needs something this
list does not carry, the list grows deliberately.
"""

from keelline.scaffold.engine import apply, plan, shipped_profiles, validate_sources
from keelline.scaffold.entries import apply_entries, mark, marker_id, owned, owned_ids
from keelline.scaffold.manifest import (
    FORMAT,
    MANIFEST_PATH,
    Kind,
    Location,
    Manifest,
    Record,
    digest,
)
from keelline.scaffold.model import Action, Applied, Plan, Refused, Template, Verb
from keelline.scaffold.regions import Style, drop, extract, upsert
from keelline.scaffold.report import render_report

__all__ = [
    "FORMAT",
    "MANIFEST_PATH",
    "Action",
    "Applied",
    "Kind",
    "Location",
    "Manifest",
    "Plan",
    "Record",
    "Refused",
    "Style",
    "Template",
    "Verb",
    "apply",
    "apply_entries",
    "digest",
    "drop",
    "extract",
    "mark",
    "marker_id",
    "owned",
    "owned_ids",
    "plan",
    "render_report",
    "shipped_profiles",
    "upsert",
    "validate_sources",
]
