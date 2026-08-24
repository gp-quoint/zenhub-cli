"""Tests for create-time body resolution (-f / --stdin / --description)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests._fixtures import make_ctx
from zh.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _patch_create_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr(
        "zh.commands.create.create_issue",
        lambda ctx, **kwargs: {"number": 42, "url": "https://example/42", **kwargs},
    )
    monkeypatch.setattr("zh.commands.create.optional_duplicate_check", lambda **_: None)


def test_create_reads_body_from_file(tmp_path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    body_file = tmp_path / "body.md"
    body_file.write_text("Hello from file", encoding="utf-8")
    captured: dict[str, str] = {}

    def _create(ctx, **kwargs):
        captured["body"] = kwargs["body"]
        return {"number": 42, "url": "https://example/42"}

    _patch_create_deps(monkeypatch)
    monkeypatch.setattr("zh.commands.create.create_issue", _create)

    result = runner.invoke(app, ["-r", "acme/widgets", "create", "Title", "-f", str(body_file)])
    assert result.exit_code == 0, result.output
    assert captured["body"] == "Hello from file"


def test_create_description_alias(tmp_path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def _create(ctx, **kwargs):
        captured["body"] = kwargs["body"]
        return {"number": 42, "url": "https://example/42"}

    _patch_create_deps(monkeypatch)
    monkeypatch.setattr("zh.commands.create.create_issue", _create)

    result = runner.invoke(app, ["-r", "acme/widgets", "create", "Title", "--description", "Long body"])
    assert result.exit_code == 0, result.output
    assert captured["body"] == "Long body"


def test_create_file_overrides_inline_body(tmp_path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    body_file = tmp_path / "body.md"
    body_file.write_text("from file", encoding="utf-8")
    captured: dict[str, str] = {}

    def _create(ctx, **kwargs):
        captured["body"] = kwargs["body"]
        return {"number": 42, "url": "https://example/42"}

    _patch_create_deps(monkeypatch)
    monkeypatch.setattr("zh.commands.create.create_issue", _create)

    result = runner.invoke(
        app,
        ["-r", "acme/widgets", "create", "Title", "-b", "inline", "-f", str(body_file)],
    )
    assert result.exit_code == 0, result.output
    assert captured["body"] == "from file"


def test_epic_create_reads_body_from_file(tmp_path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    body_file = tmp_path / "epic.md"
    body_file.write_text("Epic scope", encoding="utf-8")
    captured: dict[str, str] = {}

    def _create(ctx, **kwargs):
        captured["body"] = kwargs["body"]
        return {"number": 7, "url": "https://example/7"}

    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr("zh.commands.planning_handlers.create_issue", _create)
    monkeypatch.setattr("zh.commands.planning_handlers.optional_duplicate_check", lambda **_: None)
    monkeypatch.setattr(
        "zh.commands.planning_handlers.ensure_type_for_create",
        lambda ctx, type_name: None,
    )

    result = runner.invoke(app, ["-r", "acme/widgets", "epic", "create", "Epic title", "-f", str(body_file)])
    assert result.exit_code == 0, result.output
    assert captured["body"] == "Epic scope"
