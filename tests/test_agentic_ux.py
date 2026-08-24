"""Agentic UX: move honesty, pipeline match, sprint add order, cache invalidation."""

from __future__ import annotations

import pytest
from tests._fixtures import make_ctx
from typer.testing import CliRunner

from zh.api import ZhApiError, clear_api_caches, graphql_request
from zh.cli.main import app
from zh.issue_ops import move_issue
from zh.workspace_ops import find_pipeline_id, resolve_pipeline


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _pipelines():
    return [
        {"id": "p-new", "name": "New Issues"},
        {"id": "p-ip", "name": "In Progress"},
        {"id": "p-done", "name": "Done (in Preprod)"},
    ]


def test_resolve_pipeline_exact_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.workspace_ops.list_pipelines", lambda _ctx: _pipelines())
    ctx = make_ctx()
    assert resolve_pipeline(ctx, "in progress")["id"] == "p-ip"
    assert find_pipeline_id(ctx, "IN PROGRESS") == "p-ip"


def test_resolve_pipeline_unique_substring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.workspace_ops.list_pipelines", lambda _ctx: _pipelines())
    ctx = make_ctx()
    assert resolve_pipeline(ctx, "progress")["id"] == "p-ip"


def test_resolve_pipeline_unique_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.workspace_ops.list_pipelines", lambda _ctx: _pipelines())
    ctx = make_ctx()
    # "in" uniquely prefixes "In Progress" (not "Done (in Preprod)")
    assert resolve_pipeline(ctx, "in")["id"] == "p-ip"


def test_resolve_pipeline_ambiguous_substring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.workspace_ops.list_pipelines", lambda _ctx: _pipelines())
    ctx = make_ctx()
    with pytest.raises(ZhApiError, match="ambiguous"):
        resolve_pipeline(ctx, "e")


def test_resolve_pipeline_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.workspace_ops.list_pipelines", lambda _ctx: _pipelines())
    ctx = make_ctx()
    with pytest.raises(ZhApiError, match="not found"):
        resolve_pipeline(ctx, "backlog")


def test_move_issue_reports_real_from_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = make_ctx()
    calls: list[str] = []

    def _query(query: str, variables=None):
        calls.append(query)
        if "mutation" in query.lstrip()[:20].lower() or query.lstrip().startswith("mutation"):
            return {
                "data": {
                    "moveIssue": {
                        "issue": {
                            "pipelineIssues": {"nodes": [{"pipeline": {"name": "In Progress"}}]},
                        }
                    }
                }
            }
        if "pipelineIssues" in query and "totalCount" in query:
            return {
                "data": {
                    "issueByInfo": {
                        "id": "issue-1",
                        "number": 42,
                        "title": "Libs",
                        "pipelineIssues": {
                            "nodes": [
                                {
                                    "pipeline": {
                                        "id": "p-new",
                                        "name": "New Issues",
                                        "issues": {"totalCount": 3},
                                    }
                                }
                            ]
                        },
                    }
                }
            }
        return {"data": {"issueByInfo": {"id": "issue-1", "number": 42, "title": "Libs"}}}

    monkeypatch.setattr(ctx, "execute", lambda query, variables=None, **_: _query(query, variables)["data"])
    monkeypatch.setattr("zh.issue_ops.find_pipeline_id", lambda _c, _n: "p-ip")
    monkeypatch.setattr(
        "zh.issue_ops.get_issue_by_info",
        lambda _c, _n: {"id": "issue-1", "number": 42, "title": "Libs"},
    )

    result = move_issue(ctx, 42, "In Progress")
    assert result["from_pipeline"] == "New Issues"
    assert result["to_pipeline"] == "In Progress"
    assert result["number"] == "42"


def test_move_cmd_json(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr(
        "zh.commands.issues.move_issue",
        lambda _ctx, _num, _pipe: {
            "number": "42",
            "title": "Libs",
            "from_pipeline": "New Issues",
            "to_pipeline": "In Progress",
        },
    )
    result = runner.invoke(app, ["-r", "acme/widgets", "move", "42", "In Progress", "--json"])
    assert result.exit_code == 0, result.output
    assert '"from": "New Issues"' in result.output
    assert '"to": "In Progress"' in result.output
    assert '"ok": true' in result.output


def test_sprint_add_subcommand_first(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    captured: dict[str, object] = {}

    def _add(_ctx, sprint_name: str, nums: list[int]):
        captured["sprint"] = sprint_name
        captured["nums"] = nums
        return {"outcome": "ok", "success_count": len(nums)}

    monkeypatch.setattr("zh.commands.sprints.add_issues_to_sprint", _add)
    result = runner.invoke(app, ["-r", "acme/widgets", "sprint", "add", "current", "42"])
    assert result.exit_code == 0, result.output
    assert captured == {"sprint": "current", "nums": [42]}


def test_sprint_show_via_default_command(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr(
        "zh.commands.sprints.get_current_sprint",
        lambda _ctx: {"sprint_name": "Sprint 7", "issues": [{"number": 1, "title": "A"}]},
    )
    result = runner.invoke(app, ["-r", "acme/widgets", "sprint", "current"])
    assert result.exit_code == 0, result.output
    assert "Sprint 7" in result.output
    assert "#1" in result.output


def test_mutation_invalidates_process_read_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZH_GRAPHQL_CACHE", "0")
    clear_api_caches()
    calls = 0

    def _direct(query, variables=None, *, token, timeout=30.0, url=None):
        nonlocal calls
        calls += 1
        return {"data": {"ok": True, "n": calls}}

    monkeypatch.setattr("zh.api._graphql_request_direct", _direct)

    graphql_request("query { viewer { id } }", {}, token="tok")
    graphql_request("query { viewer { id } }", {}, token="tok")
    assert calls == 1

    graphql_request("mutation { x }", {}, token="tok")
    assert calls == 2

    graphql_request("query { viewer { id } }", {}, token="tok")
    assert calls == 3
