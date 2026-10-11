"""keelline was renamed to stayfixed: https://github.com/stayfixed/stayfixed

Installing this package installs stayfixed. The `keelline` command prints a notice and then
runs `stayfixed` with the same arguments, so scripts that still call the old name keep working.
"""

import sys

__version__ = "0.0.1"

NOTICE = "keelline was renamed to stayfixed; running `stayfixed` instead. See https://github.com/stayfixed/stayfixed"


def main() -> int:
    from stayfixed.cli import main as stayfixed_main

    print(NOTICE, file=sys.stderr)
    return stayfixed_main()
