"""Regression: zh close accepts -f/-m/--stdin and --json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests._fixtures import make_ctx
from zh.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _patch_close_deps(monkeypatch: pytest.MonkeyPatch, close_kwargs: dict[str, object]) -> None:
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())

    def _close(owner_repo: str, number: int, *, comment: str = "", reason: str = "completed") -> None:
        close_kwargs.update(owner_repo=owner_repo, number=number, comment=comment, reason=reason)

    monkeypatch.setattr("zh.commands._close_reopen.gh_issue_close", _close)
    monkeypatch.setattr(
        "zh.commands._close_reopen.gh_issue_view",
        lambda *_a, **_k: {"title": "Preproduction cleanup", "state": "OPEN"},
    )
    monkeypatch.setattr(
        "zh.commands._close_reopen.issue_zenhub_summary",
        lambda *_a, **_k: {"pipeline": "Done (in Preprod)"},
    )


def test_close_file_body(tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    body_file = tmp_path / "close.md"
    body_file.write_text("Merged PR #44 into develop.\n\nTicket done.", encoding="utf-8")
    close_kwargs: dict[str, object] = {}
    _patch_close_deps(monkeypatch, close_kwargs)

    result = runner.invoke(
        app,
        ["-r", "acme/widgets", "close", "41", "-r", "completed", "-f", str(body_file)],
    )
    assert result.exit_code == 0, result.output
    assert close_kwargs == {
        "owner_repo": "acme/widgets",
        "number": 41,
        "comment": "Merged PR #44 into develop.\n\nTicket done.",
        "reason": "completed",
    }
    assert "closed #41" in result.output.lower()


def test_close_json_shape(tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    body_file = tmp_path / "close.md"
    body_file.write_text("done via develop merge", encoding="utf-8")
    close_kwargs: dict[str, object] = {}
    _patch_close_deps(monkeypatch, close_kwargs)

    result = runner.invoke(
        app,
        ["-r", "acme/widgets", "close", "41", "-f", str(body_file), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {
        "ok": True,
        "number": 41,
        "title": "Preproduction cleanup",
        "state": "CLOSED",
        "reason": "completed",
        "comment_added": True,
        "pipeline": "Done (in Preprod)",
    }
    assert close_kwargs["comment"] == "done via develop merge"


def test_close_positional_one_liner(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    close_kwargs: dict[str, object] = {}
    _patch_close_deps(monkeypatch, close_kwargs)
    result = runner.invoke(app, ["-r", "acme/widgets", "close", "41", "shipped"])
    assert result.exit_code == 0, result.output
    assert close_kwargs["comment"] == "shipped"
    assert close_kwargs["reason"] == "completed"


def test_close_message_flag(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    close_kwargs: dict[str, object] = {}
    _patch_close_deps(monkeypatch, close_kwargs)
    result = runner.invoke(app, ["-r", "acme/widgets", "close", "41", "-m", "one liner", "-r", "not planned"])
    assert result.exit_code == 0, result.output
    assert close_kwargs["comment"] == "one liner"
    assert close_kwargs["reason"] == "not planned"


def test_close_json_without_comment(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    close_kwargs: dict[str, object] = {}
    _patch_close_deps(monkeypatch, close_kwargs)
    result = runner.invoke(app, ["-r", "acme/widgets", "close", "41", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["comment_added"] is False
    assert payload["state"] == "CLOSED"
    assert close_kwargs["comment"] == ""


def test_reopen_json(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    reopen_kwargs: dict[str, object] = {}

    def _reopen(owner_repo: str, number: int) -> None:
        reopen_kwargs.update(owner_repo=owner_repo, number=number)

    monkeypatch.setattr("zh.commands._close_reopen.gh_issue_reopen", _reopen)
    monkeypatch.setattr(
        "zh.commands._close_reopen.gh_issue_view",
        lambda *_a, **_k: {"title": "Preproduction cleanup", "state": "CLOSED"},
    )
    result = runner.invoke(app, ["-r", "acme/widgets", "reopen", "41", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {
        "ok": True,
        "number": 41,
        "title": "Preproduction cleanup",
        "state": "OPEN",
    }
    assert reopen_kwargs == {"owner_repo": "acme/widgets", "number": 41}


def test_close_help_lists_json_and_body_flags(runner: CliRunner) -> None:
    result = runner.invoke(app, ["close", "--help"])
    assert result.exit_code == 0, result.output
    assert "--json" in result.output
    assert "-f" in result.output or "--file" in result.output
    assert "--stdin" in result.output
    assert "-m" in result.output or "--message" in result.output
