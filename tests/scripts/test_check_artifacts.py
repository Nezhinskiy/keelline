"""D5: nothing inspected a built artifact. `resources.files` resolves to the checkout under
`uv run`, so a `uv_build` change that dropped the template tree from the wheel would break
`overlay create --local` for every installed user while every test stayed green."""

from __future__ import annotations

import importlib.util
import io
import sys
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

from keelline.overlay.layout import OVERLAY_FILES
from keelline.scaffold import MANIFEST_PATH

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_artifacts.py"


def checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_artifacts_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_artifacts_under_test"] = module
    spec.loader.exec_module(module)
    return module


def _wheel(path: Path, *, without: str | None = None) -> Path:
    names = [
        "keelline/presets/recommended.toml",
        *(f"keelline/templates/overlay/{r}" for r in OVERLAY_FILES),
    ]
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            if name != without:
                archive.writestr(name, "x")
    return path


def _sdist(
    path: Path, module: ModuleType, *, wrapper_mode: int = 0o755, without: str | None = None
) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for name in module.SDIST_MUST:
            if name == without:
                continue
            info = tarfile.TarInfo(f"keelline-0.0.0/{name}")
            info.size = 1
            info.mode = wrapper_mode if name in module.SDIST_EXECUTABLE else 0o644
            archive.addfile(info, io.BytesIO(b"x"))
    return path


def test_complete_artifacts_have_no_findings(tmp_path: Path) -> None:
    module = checker()
    assert module.check_wheel(_wheel(tmp_path / "k.whl")) == []
    assert module.check_sdist(_sdist(tmp_path / "k.tar.gz", module)) == []


def test_a_template_file_missing_from_the_wheel_is_named(tmp_path: Path) -> None:
    # Mutation: none of its own — the wheel check is a set difference; the sdist mode check
    # below carries the declared mutation.
    module = checker()
    missing = f"keelline/templates/overlay/{OVERLAY_FILES[-1]}"
    findings = module.check_wheel(_wheel(tmp_path / "k.whl", without=missing))
    assert findings == [f"wheel: missing {missing}"]


def test_a_wrapper_that_lost_its_executable_bit_in_the_sdist_is_named(tmp_path: Path) -> None:
    # `tar` preserves the mode, and a downstream packager unpacks it: a wrapper at 0644 exits
    # 126 for every hook entry, which Claude Code reads as permission.
    # Mutation (declared): drop the mode check -> this reddens.
    module = checker()
    findings = module.check_sdist(_sdist(tmp_path / "k.tar.gz", module, wrapper_mode=0o644))
    assert findings == [f"sdist: {name} is not executable" for name in module.SDIST_EXECUTABLE]


def test_a_rendered_overlay_is_exactly_the_shipped_files_plus_the_manifest(tmp_path: Path) -> None:
    module = checker()
    root = tmp_path / "rendered"
    for relative in (*OVERLAY_FILES, str(MANIFEST_PATH)):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text("x", encoding="utf-8")
    # The walk is stated non-empty before anything is concluded from a difference of sets:
    # `check_render` reads `root.rglob("*")`, and a walk that found nothing is the one input
    # that can make a set comparison agree for the wrong reason.
    assert [p for p in root.rglob("*") if p.is_file()]
    assert module.check_render(root) == []
    (root / "extra.txt").write_text("x", encoding="utf-8")
    assert module.check_render(root) == ["rendered: unexpected extra.txt"]


def test_rendered_without_a_directory_is_the_usage_message_and_not_a_dist_walk(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # `rendered` on its own used to fall into the `dist` branch and be globbed as a directory
    # name, so the user was told "expected exactly one wheel and one sdist under rendered"
    # about an argument they had not given. The assertion is on which sentence comes back,
    # because both forms exit 2.
    # Mutation (declared): restore `and len(argv) == 2` in the arm's condition -> the bare
    # `rendered` falls into the `dist` branch again and the first assertion reddens.
    module = checker()
    assert module.main(["rendered"]) == 2
    printed = capsys.readouterr().err
    assert "expected exactly one wheel and one sdist" not in printed
    assert "check_artifacts.py rendered DIR" in printed
