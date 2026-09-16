"""The bug ledger: one file per bug under `[paths] bugs`, one generated index at
`[paths] bug_index`, and the scan that keeps every identifier in the tree pointing at an entry.

The import surface is `keelline.ledger.api`, not this file — see `tests/ledger/test_surface.py`
for why the package `__init__` stays empty.
"""
