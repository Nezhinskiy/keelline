"""What every test runs under: a `HOME` of its own, so the product's own `git` reads no developer
configuration.

`tests/gitfixture.py` seals the `git` a fixture runs (`GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM`
at `os.devnull`, `HOME` under `tmp_path`). The `git` the product runs is another matter:
`keelline.gitenv.scrubbed_env` keeps `HOME` on purpose, because a real user's global excludes
and configuration are theirs to have honoured, and it drops every `GIT_CONFIG_*` variable. So
under test that `git` read the developer's `~/.gitconfig` and `~/.config/git/ignore`: with
`CLAUDE.md` in a global excludes file, `check-ignore` answered differently and the project
tests failed by the dozen on one machine and passed on the next.

Here, rather than in the product, because the product's behaviour for a real user is right; it
is the suite that must not depend on whose machine it runs on. `HOME` points at an empty
directory for each test and `XDG_CONFIG_HOME`, which `git` reads before `HOME/.config`, is
dropped. A test that needs a global configuration writes one into that directory. What `HOME`
cannot seal is git's system configuration, which `scrubbed_env` gives no variable to redirect;
no shipped system file carries an excludes rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _a_home_of_its_own(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return home
