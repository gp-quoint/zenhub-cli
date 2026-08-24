"""Regression: zh comment accepts -f/-m after the issue number."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests._fixtures import make_ctx
from zh.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _patch_comment_deps(monkeypatch: pytest.MonkeyPatch, captured: dict[str, object]) -> None:
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())

    def _comment(owner_repo: str, number: int, body: str) -> None:
        captured["owner_repo"] = owner_repo
        captured["number"] = number
        captured["body"] = body

    monkeypatch.setattr("zh.commands.issues.gh_issue_comment", _comment)


def test_comment_file_after_issue(tmp_path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    body_file = tmp_path / "note.md"
    body_file.write_text("from file after issue", encoding="utf-8")
    captured: dict[str, object] = {}
    _patch_comment_deps(monkeypatch, captured)

    result = runner.invoke(app, ["-r", "acme/widgets", "comment", "42", "-f", str(body_file)])
    assert result.exit_code == 0, result.output
    assert captured == {"owner_repo": "acme/widgets", "number": 42, "body": "from file after issue"}


def test_comment_file_before_issue(tmp_path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    body_file = tmp_path / "note.md"
    body_file.write_text("from file before issue", encoding="utf-8")
    captured: dict[str, object] = {}
    _patch_comment_deps(monkeypatch, captured)

    result = runner.invoke(app, ["-r", "acme/widgets", "comment", "-f", str(body_file), "42"])
    assert result.exit_code == 0, result.output
    assert captured["body"] == "from file before issue"


def test_comment_message_after_issue(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _patch_comment_deps(monkeypatch, captured)

    result = runner.invoke(app, ["-r", "acme/widgets", "comment", "42", "-m", "short note"])
    assert result.exit_code == 0, result.output
    assert captured["body"] == "short note"


def test_comment_positional_text(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _patch_comment_deps(monkeypatch, captured)

    result = runner.invoke(app, ["-r", "acme/widgets", "comment", "42", "Fixed in PR #99"])
    assert result.exit_code == 0, result.output
    assert captured["body"] == "Fixed in PR #99"


def test_comment_explicit_add_subcommand(tmp_path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    body_file = tmp_path / "note.md"
    body_file.write_text("via add", encoding="utf-8")
    captured: dict[str, object] = {}
    _patch_comment_deps(monkeypatch, captured)

    result = runner.invoke(app, ["-r", "acme/widgets", "comment", "add", "42", "-f", str(body_file)])
    assert result.exit_code == 0, result.output
    assert captured["body"] == "via add"


def test_comment_edit_still_a_subcommand(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr("zh.commands.issues.gh_current_user", lambda: "alice")
    monkeypatch.setattr(
        "zh.commands.issues.gh_fetch_issue_comments",
        lambda *_: [{"id": 9, "user": "alice", "body": "old", "createdAt": "t"}],
    )
    monkeypatch.setattr("zh.commands._issue_body.edit_text", lambda body: body + "\nedited")
    patched: dict[str, object] = {}

    def _edit(owner_repo: str, comment_id: int, body: str) -> None:
        patched.update(owner_repo=owner_repo, comment_id=comment_id, body=body)

    monkeypatch.setattr("zh.commands.issues.gh_edit_comment", _edit)

    result = runner.invoke(app, ["-r", "acme/widgets", "comment", "edit", "42", "1"])
    assert result.exit_code == 0, result.output
    assert patched["comment_id"] == 9
    assert patched["body"] == "old\nedited"


def test_c_alias_file_after_issue(tmp_path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    body_file = tmp_path / "note.md"
    body_file.write_text("via c", encoding="utf-8")
    captured: dict[str, object] = {}
    _patch_comment_deps(monkeypatch, captured)

    result = runner.invoke(app, ["-r", "acme/widgets", "c", "42", "-f", str(body_file)])
    assert result.exit_code == 0, result.output
    assert captured["body"] == "via c"
