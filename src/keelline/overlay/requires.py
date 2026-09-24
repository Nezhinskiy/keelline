"""What an overlay declares it needs, and whether a running Keelline meets it (P6).

The declaration is read in the one form the template ships, `>=X.Y.Z`, and no other: a caller
that wants a different comparison has a different question, and answering it here would grow
a parser nothing has asked for yet. `requires_of`'s return value is the normalised string a
caller may print — it is what the overlay itself declared, stripped, not a value this module
built out of parts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from keelline.overlay.layout import PLUGIN_MANIFEST

# Nine ASCII digits a component, and both halves of that bound are load-bearing.
#
# *Bounded*, because `int()` is not total. CPython 3.11 caps integer-string conversion at 4300
# digits, so an unbounded `(\d+)` let a manifest declare `>=999…9.0.0` and made `satisfies`
# raise `ValueError` out of a function whose docstring promises `None` for anything it cannot
# read. `doctor` rendered that as "this check could not run: ValueError", and the session
# handler's `except Exception` swallowed it whole — taking `NOT_ATTACHED` and every other line
# of the same result with it, so an overlay manifest silenced the one line that says the
# project is not attached. Nine digits is past every version anyone releases and far under the
# cap, and the value that exceeds it is now unreadable rather than fatal.
#
# *ASCII*, because `\d` is not. It matches every Unicode decimal digit and `int()` accepts
# them, so a floor spelled in Eastern Arabic-Indic numerals validated, compared as `>=1.0.0`,
# and printed back verbatim into a session line and a `doctor` row — `requires_of` returns the
# overlay's own bytes, and "the one owner-authored string that prints" is meant to be a
# version, not an arbitrary numeral system. `tests/overlay/test_requires.py` spells the digits.
_COMPONENT = r"([0-9]{1,9})"
_FLOOR = re.compile(rf"^>={_COMPONENT}\.{_COMPONENT}\.{_COMPONENT}$")
_VERSION = re.compile(rf"^{_COMPONENT}\.{_COMPONENT}\.{_COMPONENT}")
# What may follow an `X.Y.Z` in a pre-release of it: PEP 440's `a`, `b`, `rc` and `dev` segments
# and their spellings, with an optional separator (`1.0.0rc1`, `1.0.0-rc.1`, `0.2.0.dev0`). The
# whole suffix must be one of them, so `1.0.0rc1.post2` is not read as a pre-release.
_PRE_RELEASE = re.compile(
    r"\A[-_.]?(?:a|alpha|b|beta|c|rc|pre|preview|dev)[-_.]?[0-9]{0,9}"
    r"(?:[-_.]?dev[-_.]?[0-9]{0,9})?\Z",
    re.IGNORECASE,
)


def requires_of(root: Path) -> str | None:
    """The `keelline.requires` string an overlay's manifest declares, stripped.

    `None` when the manifest is absent, unreadable, or does not carry a non-empty string —
    every one of those is "nothing declared", and none of them is this reader's business to
    tell apart.
    """
    path = root / PLUGIN_MANIFEST
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    head = raw.get("keelline")
    value = head.get("requires") if isinstance(head, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def satisfies(spec: str, version: str) -> bool | None:
    """`True`/`False` for `>=X.Y.Z` against an `X.Y.Z[...]` version, compared as integer tuples.

    `None` for any other spec shape or a version this reader cannot parse — a caller that gets
    `None` back has an unreadable declaration, not a false one.

    **It answers, for every string.** `None` is the whole of "this reader cannot read it", and
    the two grammars above are what make that true: every component they admit is an integer
    `int()` converts, so no input reaches this function's arithmetic that could raise out of it.
    Both callers rest on that — `doctor`'s row turns an exception into "this check could not
    run", and the session handler's backstop turns one into silence for the whole line — so a
    reader that raises for an input a repository or an owner can write is a reader that deletes
    the lines around it.
    """
    floor = _FLOOR.match(spec)
    running = _VERSION.match(version)
    if floor is None or running is None:
        return None
    return tuple(int(part) for part in running.groups()) >= tuple(
        int(part) for part in floor.groups()
    )


def later(version: str, than: str) -> bool | None:
    """Whether `version` is later than `than`, by the leading `X.Y.Z` and then by what follows it.

    Both are read the way `satisfies` reads a running version: the leading three components,
    compared as integer tuples, decide whenever they differ, so `1.0.0-rc1` is later than
    `0.9.9`. `None` when either has no leading `X.Y.Z` (`v1.0.0`, an empty string): the
    direction is unknown, and a caller that would move a value in one direction must not guess
    it. `keelline upgrade` refuses such a recorded version, and `doctor`'s `versions` row says so
    rather than sending it there.

    **Equal triples are not equal versions.** Read by the triple alone, `later('1.0.0',
    '1.0.0rc1')` was `False`, so a pre-release build moved a project recording the release down
    to the pre-release and re-pinned it. With the triples equal, a bare version is later than one
    carrying a pre-release suffix (`_PRE_RELEASE`: `a`, `b`, `rc`, `dev` and their spellings),
    and one pre-release is never later than the bare release. Any other pair of different
    strings — two pre-releases, or a suffix that is not a pre-release, such as `.post1` or
    `+local`, which is later than the bare version — is `None`: this reader orders no suffix it
    does not have to, and a caller refuses rather than guess. A version is never later than
    itself, so `later(v, v)` is `False` exactly when `v` is readable.
    """
    first = _VERSION.match(version)
    second = _VERSION.match(than)
    if first is None or second is None:
        return None
    ours = tuple(int(part) for part in first.groups())
    theirs = tuple(int(part) for part in second.groups())
    if ours != theirs:
        return ours > theirs
    suffix, other = version[first.end() :], than[second.end() :]
    if suffix == other:
        return False
    if not suffix and _PRE_RELEASE.match(other):
        return True
    if not other and _PRE_RELEASE.match(suffix):
        return False
    return None
