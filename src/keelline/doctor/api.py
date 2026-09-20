"""The doctor area's import surface: everything another lane may import from it.

The command module in this area is its first consumer. A lane that needs something absent from
this list grows it deliberately, in a commit that says which lane and why — it does not import
a private module of this area.

Every name below is here for a reason written beside it, because a surface that survives a trim
with no explanation is what made the trim necessary:

- `run_checks` is the report, and `Check` is the row it is made of — a return type absent from
  this list is a value a consumer can hold and cannot declare, which is the one thing a surface
  exists to prevent. `tests/test_surfaces.py` derives that rule rather than restating it.
- `OK`, `WARN`, `RED`, `SKIP` and the `STATUSES` they belong to are `Check.status`'s closed
  vocabulary, and the set is the export rather than the members that have a caller today, for
  the reason `attach/api.py` gives about `Binding.state`: half a closed vocabulary cannot be
  read by the consumer that gets a value from it. `tests/test_install_path.py` branches on
  `RED` and `SKIP` through this surface already.

`plugin_root` was on this list and is not any more: nothing outside this area imports it, and
the one test that reads it takes it from `keelline.doctor.checks`, which is its own area's
module and nobody else's business.

**Trimmed, in the wave-4 surface trim.** `SETTINGS_FILES` — the three settings files
`_hook_entries` walks — had no importer outside this area in `src/`, `scripts/` or `tests/`, no
exported signature naming it, and no reader reaching it by string. It was grouped on this list
under "the report and the row it is made of" and is neither: it is the walk's own input, read
by `checks.py` and by this area's tests from `keelline.doctor.checks`, which is where a name
with one area's readers belongs. `assess` alone is not a reason to publish one — `guards/api.py`
made that ruling over twenty-nine names, and a lane that does not exist yet grows this list when
it arrives.
"""

from keelline.doctor.checks import OK, RED, SKIP, STATUSES, WARN, Check, run_checks

__all__ = [
    "OK",
    "RED",
    "SKIP",
    "STATUSES",
    "WARN",
    "Check",
    "run_checks",
]
