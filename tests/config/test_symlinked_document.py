"""A `keelline.toml` that is a symlink, met by every command family that loads the configuration.

There were two readers of the file: `keelline gate`, `assess` and `init` went through
`read_document`, which refuses a symlink, and every other command through a plain `read_text`,
which follows one. A clone's `keelline.toml -> /dev/zero` then kept `adopt`, `bugs check` and
`plan check` reading until the machine ran out of memory. `load` now reads through
`read_document`, so each family below is refused before anything is read. The link here points
at a valid document, so a reader that follows it would load it and go on: the refusal is the
only thing that can make these cases pass, and a regression cannot hang the suite.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run
from keelline.config.loader import CONFIG_FILE, load
from keelline.config.paths import PathEscape
from tests.gitfixture import git, needs_git

pytestmark = needs_git

DOCUMENT = '[keelline]\nversion = "0.1.0"\n\n[project]\nname = "widget"\n'


def _linked(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    outside = tmp_path / "outside.toml"
    outside.write_text(DOCUMENT, encoding="utf-8")
    (root / CONFIG_FILE).symlink_to(outside)
    return root


def test_load_refuses_a_symlinked_keelline_toml(tmp_path: Path) -> None:
    # Mutation (declared): `load` reading the file with a plain `read_text` again -> it follows
    # the link and loads the document outside.
    with pytest.raises(PathEscape):
        load(_linked(tmp_path), machine=tmp_path / "absent.toml")


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(
            ["adopt", "begin", "docs/plans/2026-09-26-keelline-adoption.md"], id="adopt-begin"
        ),
        pytest.param(["adopt", "promote"], id="adopt-promote"),
        pytest.param(["bugs", "check"], id="bugs-check"),
        pytest.param(["plan", "check"], id="plan-check"),
        pytest.param(["docs", "check"], id="docs-check"),
        pytest.param(["docs", "trail", "--check"], id="docs-trail"),
        pytest.param(["assess"], id="assess"),
        pytest.param(["gate"], id="gate"),
    ],
)
def test_every_command_family_refuses_a_symlinked_keelline_toml(
    tmp_path: Path, argv: list[str]
) -> None:
    root = _linked(tmp_path)
    parser = build_parser(discover_registrars())
    flags = ["--root", str(root), "--machine", str(tmp_path / "absent.toml")]
    with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
        code = run([*argv, *flags], parser=parser)
    assert code == 2, err.getvalue()
    assert f"{CONFIG_FILE!r} passes through a symlink" in err.getvalue()
    assert out.getvalue() == ""
