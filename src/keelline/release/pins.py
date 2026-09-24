"""Which commit a release is, asked of the public repository, for an immutable pin (principle 9).

The sha `init` writes into a project's workflow has to be one a release actually is, and
`doctor` has to be able to say whether a recorded one still is: one `git ls-remote` over
`refs/tags/v*`, annotated tags peeled to the commit they name. The repository is
`keelline.REPOSITORY_URL` and the pattern is a constant, which is what lets either stand in a
subprocess's argument list (principle 5).

`released` distinguishes three states — could not ask (`None`), no tags at all (`{}`), and a
listing that may or may not hold the tag asked for — and **its callers tell two of them apart, not
three.** `resolve_pin` answers `Resolution(None, True)` for "no such tag" and for "no tags at all"
alike, and `project.templates._ci` prints one sentence for both (`NO_TAG`) and another for the
failed ask (`NOT_ASKED`); `doctor`'s `ci-ref` row splits the same two ways. The `{}` arm exists so
that `git ls-remote --exit-code`'s non-zero exit for "nothing matched" cannot be read as a failed
ask, which is the distinction every caller does depend on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from keelline import REPOSITORY_URL
from keelline.release.versions import tag_for
from keelline.runner import Runner

TAGS = "refs/tags/v*"
NO_MATCH = 2
_LINE = re.compile(r"^([0-9a-f]{40})\trefs/tags/(v[0-9][0-9A-Za-z.-]*?)(\^\{\})?$")
_SEMVER = re.compile(r"^v\d+\.\d+\.\d+$")


@dataclass(frozen=True)
class Pin:
    tag: str
    sha: str


@dataclass(frozen=True)
class Resolution:
    pin: Pin | None
    asked: bool


def released(runner: Runner, *, cwd: Path) -> dict[str, str] | None:
    done = runner.run(["git", "ls-remote", "--exit-code", REPOSITORY_URL, TAGS], cwd)
    if done.code == NO_MATCH and not done.stdout.strip():
        return {}
    if done.code != 0:
        return None
    plain: dict[str, str] = {}
    peeled: dict[str, str] = {}
    for line in done.stdout.splitlines():
        match = _LINE.match(line.strip())
        if match is None:
            continue
        sha, tag, is_peeled = match.groups()
        (peeled if is_peeled else plain)[tag] = sha
    return {**plain, **peeled}


def resolve_pin(version: str, runner: Runner, *, cwd: Path) -> Resolution:
    pins = released(runner, cwd=cwd)
    if pins is None:
        return Resolution(None, False)
    tag = tag_for(version)[0]
    return Resolution(Pin(tag, pins[tag]) if tag in pins else None, True)


def is_released(sha: str, runner: Runner, *, cwd: Path) -> bool | None:
    pins = released(runner, cwd=cwd)
    if pins is None:
        return None
    return any(value == sha for tag, value in pins.items() if _SEMVER.match(tag))
