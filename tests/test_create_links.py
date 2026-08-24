"""Create success output includes ZenHub + GitHub links."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests._fixtures import make_ctx
from zh.cli.main import app
from zh.gh_ops import github_issue_url, zenhub_issue_url


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_github_and_zenhub_url_helpers() -> None:
    assert github_issue_url("acme/widgets", 42) == "https://github.com/acme/widgets/issues/42"
    assert (
        zenhub_issue_url("ws-123", "acme/widgets", 42)
        == "https://app.zenhub.com/workspaces/ws-123/issues/gh/acme/widgets/42"
    )


def test_create_prints_zenhub_and_github_links(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr("zh.commands.create.optional_duplicate_check", lambda **_: None)
    monkeypatch.setattr(
        "zh.commands.create.create_issue",
        lambda ctx, **kwargs: {
            "number": 42,
            "title": kwargs["title"],
            "url": "https://github.com/acme/widgets/issues/42",
            "github_url": "https://github.com/acme/widgets/issues/42",
            "zenhub_url": "https://app.zenhub.com/workspaces/ws/issues/gh/acme/widgets/42",
        },
    )

    result = runner.invoke(app, ["-r", "acme/widgets", "create", "Title", "-b", "body"])
    assert result.exit_code == 0, result.output
    combined = result.stdout + result.stderr
    assert "ZenHub: https://app.zenhub.com/workspaces/ws/issues/gh/acme/widgets/42" in combined
    assert "GitHub: https://github.com/acme/widgets/issues/42" in combined


def test_create_json_includes_both_urls(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr("zh.commands.create.optional_duplicate_check", lambda **_: None)
    monkeypatch.setattr(
        "zh.commands.create.create_issue",
        lambda ctx, **kwargs: {
            "number": 42,
            "title": kwargs["title"],
            "url": "https://github.com/acme/widgets/issues/42",
            "github_url": "https://github.com/acme/widgets/issues/42",
            "zenhub_url": "https://app.zenhub.com/workspaces/ws/issues/gh/acme/widgets/42",
        },
    )

    result = runner.invoke(app, ["-r", "acme/widgets", "create", "Title", "-b", "body", "--json"])
    assert result.exit_code == 0, result.output
    assert '"github_url": "https://github.com/acme/widgets/issues/42"' in result.stdout
    assert '"zenhub_url": "https://app.zenhub.com/workspaces/ws/issues/gh/acme/widgets/42"' in result.stdout
