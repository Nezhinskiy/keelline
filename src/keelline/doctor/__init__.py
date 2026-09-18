"""`doctor`: what an installation looks like from the outside (§8.4).

This area **reports and never repairs.** Every other area in this package writes something;
this one reads, and the one subprocess it runs is Keelline's own hook wrapper, run with
`--version` so that the only thing it can change is whether the report can say the wrapper
works. A check that cannot be answered says `skip` and names what a measurement would need —
three of the fifteen do — because a check that returned green because it could not look would
be strictly worse than one that admits it.
"""
