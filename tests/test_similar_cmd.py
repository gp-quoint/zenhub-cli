"""Tests for `zh similar` / `zh reindex` command wiring."""

from __future__ import annotations

from typer.testing import CliRunner

from zh.cli.main import app


def test_similar_uses_config_repo_not_launcher_cwd(monkeypatch, tmp_path) -> None:
    """`zh similar` must honor ZH_REPO/config like other commands.

    The bash launcher cd's into the zenhub-cli checkout before exec;
    similarity must not bypass config and fall back to that git remote.
    """
    config_dir = tmp_path / ".config" / "zh"
    config_dir.mkdir(parents=True)
    (config_dir / "config").write_text("ZH_TOKEN=fake\nZH_REPO=QuoIntelligence/quollection\n")

    captured: dict[str, str] = {}

    def fake_find_similar(query: str, repo: str, **kwargs: object) -> list[object]:
        captured["repo"] = repo
        return []

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("zh.commands.similar.find_similar", fake_find_similar)
    monkeypatch.setattr("zh.api.get_zenhub_repo_id", lambda *a, **k: "repo-id")
    monkeypatch.setattr("zh.api.get_workspace_id", lambda *a, **k: "ws-id")

    result = CliRunner().invoke(app, ["similar", "example", "--json"])
    assert result.exit_code == 0, result.output
    assert captured["repo"] == "QuoIntelligence/quollection"
