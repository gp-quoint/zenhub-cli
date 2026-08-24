"""Regression: zh comment edit accepts -f/-m/--stdin/--fill non-interactively."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests._fixtures import make_ctx
from zh.cli.main import app
from zh.commands._issue_body import apply_body_fills, comment_body_for_edit


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _patch_edit_deps(monkeypatch: pytest.MonkeyPatch, patched: dict[str, object]) -> None:
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr("zh.commands.issues.gh_current_user", lambda: "alice")
    monkeypatch.setattr(
        "zh.commands.issues.gh_fetch_issue_comments",
        lambda *_: [
            {
                "id": 9,
                "user": "alice",
                "body": "Opened PRs:\n- Python: {{PYTHON_PR}}\n- Go: {{GO_PR}}",
                "createdAt": "t",
            }
        ],
    )

    def _edit(owner_repo: str, comment_id: int, body: str) -> None:
        patched.update(owner_repo=owner_repo, comment_id=comment_id, body=body)

    monkeypatch.setattr("zh.commands.issues.gh_edit_comment", _edit)
    monkeypatch.setattr(
        "zh.commands.issues.comment_body_for_edit",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("use real helper")),
    )


def test_apply_body_fills() -> None:
    assert apply_body_fills("a={{X}} b={{Y}}", ["X=1", "Y=2"]) == "a=1 b=2"


def test_comment_body_for_edit_file(tmp_path) -> None:
    path = tmp_path / "n.md"
    path.write_text("from file", encoding="utf-8")
    assert comment_body_for_edit("old", None, path, from_stdin=False) == "from file"


def test_comment_body_for_edit_fill_only() -> None:
    old = "see {{URL}}"
    assert comment_body_for_edit(old, None, None, from_stdin=False, fills=["URL=https://x"]) == "see https://x"


def test_comment_edit_file_after_index(tmp_path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    body_file = tmp_path / "note.md"
    body_file.write_text("replaced body", encoding="utf-8")
    patched: dict[str, object] = {}
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr("zh.commands.issues.gh_current_user", lambda: "alice")
    monkeypatch.setattr(
        "zh.commands.issues.gh_fetch_issue_comments",
        lambda *_: [{"id": 9, "user": "alice", "body": "old", "createdAt": "t"}],
    )

    def _edit(owner_repo: str, comment_id: int, body: str) -> None:
        patched.update(owner_repo=owner_repo, comment_id=comment_id, body=body)

    monkeypatch.setattr("zh.commands.issues.gh_edit_comment", _edit)

    result = runner.invoke(app, ["-r", "acme/widgets", "comment", "edit", "42", "1", "-f", str(body_file)])
    assert result.exit_code == 0, result.output
    assert patched == {"owner_repo": "acme/widgets", "comment_id": 9, "body": "replaced body"}


def test_comment_edit_message(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    patched: dict[str, object] = {}
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr("zh.commands.issues.gh_current_user", lambda: "alice")
    monkeypatch.setattr(
        "zh.commands.issues.gh_fetch_issue_comments",
        lambda *_: [{"id": 9, "user": "alice", "body": "old", "createdAt": "t"}],
    )

    def _edit(owner_repo: str, comment_id: int, body: str) -> None:
        patched.update(body=body)

    monkeypatch.setattr("zh.commands.issues.gh_edit_comment", _edit)

    result = runner.invoke(app, ["-r", "acme/widgets", "comment", "edit", "42", "1", "-m", "new note"])
    assert result.exit_code == 0, result.output
    assert patched["body"] == "new note"


def test_comment_edit_fill_placeholders(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    patched: dict[str, object] = {}
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr("zh.commands.issues.gh_current_user", lambda: "alice")
    monkeypatch.setattr(
        "zh.commands.issues.gh_fetch_issue_comments",
        lambda *_: [
            {
                "id": 9,
                "user": "alice",
                "body": "Opened PRs:\n- Python: {{PYTHON_PR}}\n- Go: {{GO_PR}}",
                "createdAt": "t",
            }
        ],
    )

    def _edit(owner_repo: str, comment_id: int, body: str) -> None:
        patched.update(body=body)

    monkeypatch.setattr("zh.commands.issues.gh_edit_comment", _edit)

    result = runner.invoke(
        app,
        [
            "-r",
            "acme/widgets",
            "comment",
            "edit",
            "42",
            "1",
            "--fill",
            "PYTHON_PR=https://github.com/acme/py/pull/1",
            "--fill",
            "GO_PR=https://github.com/acme/go/pull/1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert patched["body"] == (
        "Opened PRs:\n- Python: https://github.com/acme/py/pull/1\n- Go: https://github.com/acme/go/pull/1"
    )


def test_comment_edit_stdin(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    patched: dict[str, object] = {}
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr("zh.commands.issues.gh_current_user", lambda: "alice")
    monkeypatch.setattr(
        "zh.commands.issues.gh_fetch_issue_comments",
        lambda *_: [{"id": 9, "user": "alice", "body": "old", "createdAt": "t"}],
    )

    def _edit(owner_repo: str, comment_id: int, body: str) -> None:
        patched.update(body=body)

    monkeypatch.setattr("zh.commands.issues.gh_edit_comment", _edit)

    result = runner.invoke(
        app,
        ["-r", "acme/widgets", "comment", "edit", "42", "1", "--stdin"],
        input="from stdin\n",
    )
    assert result.exit_code == 0, result.output
    assert patched["body"] == "from stdin\n"


def test_comment_edit_editor_path_unchanged(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bare edit still uses $EDITOR when no body flags."""
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr("zh.commands.issues.gh_current_user", lambda: "alice")
    monkeypatch.setattr(
        "zh.commands.issues.gh_fetch_issue_comments",
        lambda *_: [{"id": 9, "user": "alice", "body": "old", "createdAt": "t"}],
    )
    monkeypatch.setattr("zh.commands._issue_body.edit_text", lambda body: body + "\nedited")
    patched: dict[str, object] = {}

    def _edit(owner_repo: str, comment_id: int, body: str) -> None:
        patched.update(body=body)

    monkeypatch.setattr("zh.commands.issues.gh_edit_comment", _edit)

    result = runner.invoke(app, ["-r", "acme/widgets", "comment", "edit", "42", "1"])
    assert result.exit_code == 0, result.output
    assert patched["body"] == "old\nedited"
