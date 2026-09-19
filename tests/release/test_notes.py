"""`release notes`: the towncrier wrapper §5.2 lists, driven through the runner seam.

towncrier is a development dependency and is *invoked*, never imported (Global
Constraints); the argv is the contract, and a stub records it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from keelline.errors import Failure, Refusal
from keelline.release.notes import build
from keelline.runner import NOT_FOUND, Completed


@dataclass
class _Stub:
    code: int = 0
    stdout: str = "## 1.2.3\n\n- a note\n"
    calls: list[tuple[list[str], Path]] = field(default_factory=list)

    def run(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append((argv, cwd))
        return Completed(self.code, self.stdout, "" if self.code == 0 else "boom")


def _root(tmp_path: Path, version: str = "1.2.3") -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "keelline"\nversion = "{version}"\n', encoding="utf-8"
    )
    return tmp_path


def test_the_argv_is_towncriers_build_with_the_version_and_yes(tmp_path: Path) -> None:
    stub = _Stub()
    build(_root(tmp_path), version="1.2.3", draft=False, runner=stub)
    assert stub.calls == [(["towncrier", "build", "--version", "1.2.3", "--yes"], tmp_path)]


def test_a_draft_adds_the_flag_and_returns_towncriers_stdout(tmp_path: Path) -> None:
    stub = _Stub()
    assert build(_root(tmp_path), version="1.2.3", draft=True, runner=stub) == stub.stdout
    assert stub.calls[0][0][-1] == "--draft"


def test_a_version_that_is_not_the_projects_is_refused_before_anything_runs(tmp_path: Path) -> None:
    # `release check` requires the changelog's first heading to equal pyproject's version,
    # so assembling under another number writes a changelog the gate then refuses. Refused
    # here, above the write. Mutation (declared): drop the comparison -> the stub is called
    # and the `calls == []` assertion reddens.
    stub = _Stub()
    with pytest.raises(Refusal, match="set the version everywhere first"):
        build(_root(tmp_path, version="1.2.3"), version="1.3.0", draft=False, runner=stub)
    assert stub.calls == []


def test_a_missing_towncrier_names_the_dependency_group(tmp_path: Path) -> None:
    with pytest.raises(Failure, match="uv sync"):
        build(_root(tmp_path), version="1.2.3", draft=False, runner=_Stub(code=NOT_FOUND))
