"""The `bugs` group through the real frame: one line out, three exit codes, `--json`.

keelline:ledger:fixtures — the identifiers below are sample data, not claims about a ledger.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run
from keelline.findings import Finding

CONFIG = """
[keelline]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"
"""


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def project(tmp_path: Path) -> tuple[Path, list[str]]:
    root = tmp_path / "widget"
    root.mkdir()
    (root / "keelline.toml").write_text(CONFIG, encoding="utf-8")
    for name in ("src", "docs", "docs/bugs"):
        (root / name).mkdir()
    return root, ["--root", str(root), "--machine", str(tmp_path / "m.toml")]


def test_new_files_an_entry_and_prints_its_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, common = project(tmp_path)
    argv = ["bugs", "new", "a title", "--severity", "low", "--area", "an area", "--no-fetch"]
    assert invoke([*argv, *common]) == 0
    out = capsys.readouterr().out
    assert out == "filed docs/bugs/BR-001.md\n"
    assert (root / "docs" / "bug-reports.md").is_file()


def test_new_json_carries_the_identifier_and_the_fetch_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _root, common = project(tmp_path)
    argv = ["bugs", "new", "t", "--severity", "low", "--area", "a", "--no-fetch", "--json"]
    assert invoke([*argv, *common]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["id"] == "BR-001"
    assert data["path"] == "docs/bugs/BR-001.md"
    assert data["warning"] is None


def test_new_with_a_bad_severity_is_refused_by_argparse(tmp_path: Path) -> None:
    _root, common = project(tmp_path)
    with pytest.raises(SystemExit):
        invoke(["bugs", "new", "t", "--severity", "huge", "--area", "a", *common])


def test_check_is_inert_on_a_project_with_no_ledger(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, common = project(tmp_path)
    (root / "docs" / "bugs").rmdir()
    assert invoke(["bugs", "check", *common]) == 0
    assert "nothing to check" in capsys.readouterr().out


def test_check_reports_a_citation_when_there_is_no_ledger(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The gate reports it, so the command its remedy names must report it too, and not
    # answer "nothing to check".
    root, common = project(tmp_path)
    (root / "docs" / "bugs").rmdir()
    (root / "src" / "a.py").write_text("# see docs/bugs/BR-404.md\n", encoding="utf-8")
    assert invoke(["bugs", "check", *common]) == 1
    assert capsys.readouterr().out.startswith(
        "FAIL: 1 ledger problem(s): src/a.py:1 [dangling-citation]"
    )


def test_check_reports_problems_on_one_line_and_lists_them_in_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, common = project(tmp_path)
    invoke(["bugs", "new", "t", "--severity", "low", "--area", "a", "--no-fetch", *common])
    capsys.readouterr()
    (root / "src" / "a.py").write_text("# BR-404\n# BR-405\n", encoding="utf-8")
    assert invoke(["bugs", "check", *common]) == 1
    line = capsys.readouterr().out
    assert line.startswith(
        "FAIL: 2 ledger problem(s): src/a.py:1 [dangling-mention], src/a.py:2 [dangling-mention]"
    )
    # One line out (§5.2): the details that would have made it many are in `--json`.
    assert line.count("\n") == 1
    assert invoke(["bugs", "check", "--json", *common]) == 1
    data = json.loads(capsys.readouterr().out)
    # `findings` and not `problems`: one name across every command that returns a list of
    # `Finding`. Mutation: spell the key `problems` in `run_bugs_check` — this reddens.
    assert [p["rule"] for p in data["findings"]] == ["dangling-mention", "dangling-mention"]
    assert "BR-404" in data["findings"][0]["detail"]


def test_check_passes_a_clean_ledger(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _root, common = project(tmp_path)
    invoke(["bugs", "new", "t", "--severity", "low", "--area", "a", "--no-fetch", *common])
    capsys.readouterr()
    assert invoke(["bugs", "check", *common]) == 0
    assert capsys.readouterr().out == (
        "OK: bug ledger entries, index freshness, and identifier references\n"
    )


def test_index_check_reports_staleness_and_index_repairs_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, common = project(tmp_path)
    invoke(["bugs", "new", "t", "--severity", "low", "--area", "a", "--no-fetch", *common])
    (root / "docs" / "bug-reports.md").write_text("", encoding="utf-8")
    assert invoke(["bugs", "index", "--check", *common]) == 1
    assert "is stale; run: keelline bugs index" in capsys.readouterr().out
    assert invoke(["bugs", "index", *common]) == 0
    assert capsys.readouterr().out == "rewrote docs/bug-reports.md (1 entries)\n"
    assert invoke(["bugs", "index", "--check", *common]) == 0


def test_index_refuses_over_foreign_content_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, common = project(tmp_path)
    (root / "docs" / "bug-reports.md").write_text(
        "# Bug reports\n\n## BR-009 — hand-written\n", encoding="utf-8"
    )
    assert invoke(["bugs", "index", *common]) == 2
    assert "refused" in capsys.readouterr().err


def test_renumber_reports_its_endpoints(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _root, common = project(tmp_path)
    invoke(["bugs", "new", "t", "--severity", "low", "--area", "a", "--no-fetch", *common])
    capsys.readouterr()
    assert invoke(["bugs", "renumber", "BR-001", "BR-009", *common]) == 0
    assert capsys.readouterr().out == (
        "BR-001 -> BR-009; a void pointer remains at docs/bugs/BR-001.md\n"
    )


def test_a_missing_configuration_is_a_failure_not_a_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    machine = str(tmp_path / "m.toml")
    assert invoke(["bugs", "check", "--root", str(tmp_path), "--machine", machine]) == 1
    assert "failed" in capsys.readouterr().err


def test_index_writes_nothing_when_it_is_already_current(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `new` has just regenerated it, so the bare `index` has nothing to do and says so on its
    # own line rather than rewriting a file whose bytes would not change.
    root, common = project(tmp_path)
    invoke(["bugs", "new", "t", "--severity", "low", "--area", "a", "--no-fetch", *common])
    capsys.readouterr()
    before = (root / "docs" / "bug-reports.md").stat().st_mtime_ns
    assert invoke(["bugs", "index", *common]) == 0
    assert capsys.readouterr().out == "docs/bug-reports.md is current (1 entries)\n"
    assert (root / "docs" / "bug-reports.md").stat().st_mtime_ns == before


def test_renumber_fails_naming_a_file_the_sweep_could_not_rewrite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Exit 1, not 0: once the void pointer exists a stale mention in that file looks
    # intentional to `bugs check` forever, so the move is reported as incomplete.
    import os

    if os.geteuid() == 0:
        pytest.skip("root writes everywhere")
    root, common = project(tmp_path)
    invoke(["bugs", "new", "t", "--severity", "low", "--area", "a", "--no-fetch", *common])
    capsys.readouterr()
    sealed = root / "src" / "sealed"
    sealed.mkdir()
    (sealed / "a.py").write_text("# BR-001\n", encoding="utf-8")
    sealed.chmod(0o555)
    try:
        assert invoke(["bugs", "renumber", "BR-001", "BR-009", *common]) == 1
    finally:
        sealed.chmod(0o755)
    line = capsys.readouterr().out
    assert line.startswith("FAIL: BR-001 moved to BR-009, but 1 file(s) still reference BR-001")
    assert "(src/sealed/a.py)" in line and "docs/bugs/BR-001.md" in line
    assert line.count("\n") == 1


def test_check_answers_with_the_bugs_gate_s_own_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `bugs check` and the `bugs` gate are one function. Mutation
    # (advisory): the import in `run_bugs_check` becomes `from keelline.ledger.check import
    # problems as bugs_gate, uninitialised` — the patch is unseen and this reddens.
    _root, common = project(tmp_path)
    argv = ["bugs", "new", "a title", "--severity", "low", "--area", "an area", "--no-fetch"]
    assert invoke([*argv, *common]) == 0
    assert invoke(["bugs", "check", *common]) == 0
    planted = [Finding("planted", "", None, "")]
    monkeypatch.setattr("keelline.ledger.check.bugs_gate", lambda *args, **kwargs: planted)
    assert invoke(["bugs", "check", *common]) == 1
