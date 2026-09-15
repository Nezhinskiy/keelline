from __future__ import annotations

import io
import json

import pytest

from keelline.cli import build_parser, discover_registrars, run


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def feed(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_guard_bg_cleanup_refuses_a_leaking_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"tool_input": {"command": "sleep 300 & wait", "run_in_background": True}}
    feed(monkeypatch, json.dumps(payload))
    assert invoke(["guard", "bg-cleanup"]) == 2
    assert "refused:" in capsys.readouterr().err


def test_guard_bg_cleanup_accepts_a_bare_tool_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feed(monkeypatch, json.dumps({"command": "make && make test", "run_in_background": True}))
    assert invoke(["guard", "bg-cleanup"]) == 0
    assert "no background leak" in capsys.readouterr().out


def test_guard_bg_cleanup_reports_a_restore_hint_as_a_finding(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feed(monkeypatch, json.dumps({"command": "cp a a.bak; pytest; cp a.bak a"}))
    assert invoke(["guard", "bg-cleanup", "--json"]) == 1
    assert "trap" in json.loads(capsys.readouterr().out)["hint"]


def test_guard_bg_cleanup_passes_a_payload_for_another_tool_like_the_handler_does(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "x", "run_in_background": True}}
    feed(monkeypatch, json.dumps(payload))
    assert invoke(["guard", "bg-cleanup"]) == 0
    assert "not a Bash call" in capsys.readouterr().out


@pytest.mark.parametrize("stdin", ["not json at all", "[1, 2]", '{"tool_input": "x"}', "{}"])
def test_guard_bg_cleanup_refuses_what_it_cannot_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], stdin: str
) -> None:
    # Fail-closed (§5.2): a guard that cannot read its input must not answer "allowed".
    feed(monkeypatch, stdin)
    assert invoke(["guard", "bg-cleanup"]) == 2
    assert "refused" in capsys.readouterr().err
