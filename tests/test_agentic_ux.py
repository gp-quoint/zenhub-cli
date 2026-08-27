"""Agentic UX: move honesty, pipeline match, sprint add order, cache invalidation."""

from __future__ import annotations

import pytest
from tests._fixtures import make_ctx
from typer.testing import CliRunner

from zh.api import ZhApiError, clear_api_caches, graphql_request
from zh.cli.main import app
from zh.issue_ops import issue_zenhub_summary, move_issue
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
            assert variables is not None
            assert variables.get("workspaceId") == ctx.workspace_id
            return {
                "data": {
                    "moveIssue": {
                        "issue": {
                            "pipelineIssue": {"pipeline": {"name": "In Progress"}},
                            "pipelineIssues": {"nodes": [{"pipeline": {"name": "New Issues"}}]},
                        }
                    }
                }
            }
        if "pipelineIssue" in query or "IssuePipeline" in query or "estimate" in query:
            assert variables is not None
            assert variables.get("workspaceId") == ctx.workspace_id
            return {
                "data": {
                    "issueByInfo": {
                        "id": "issue-1",
                        "number": 42,
                        "title": "Libs",
                        "estimate": {"value": 8},
                        "zenhubUrl": "https://app.zenhub.com/workspaces/ws/issues/gh/acme/widgets/42",
                        "pipelineIssue": {
                            "pipeline": {
                                "id": "p-blocked",
                                "name": "Blocked",
                                "issues": {"totalCount": 5},
                            },
                            "priority": {"name": "High"},
                        },
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
    assert result["from_pipeline"] == "Blocked"
    assert result["to_pipeline"] == "In Progress"
    assert result["number"] == "42"


def test_issue_zenhub_summary_prefers_workspace_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = make_ctx()

    def _query(query: str, variables=None):
        assert variables is not None
        assert variables.get("workspaceId") == ctx.workspace_id
        return {
            "data": {
                "issueByInfo": {
                    "id": "issue-1",
                    "number": 42,
                    "title": "Libs",
                    "estimate": {"value": 8},
                    "zenhubUrl": "https://app.zenhub.com/workspaces/ws-gid-backend/issues/gh/acme/widgets/42",
                    "pipelineIssue": {
                        "pipeline": {"id": "p-b", "name": "Blocked", "issues": {"totalCount": 2}},
                        "priority": {"name": "High"},
                    },
                    "pipelineIssues": {
                        "nodes": [{"pipeline": {"id": "p-n", "name": "New Issues", "issues": {"totalCount": 9}}}]
                    },
                }
            }
        }

    monkeypatch.setattr(ctx, "execute", lambda query, variables=None, **_: _query(query, variables)["data"])
    summary = issue_zenhub_summary(ctx, 42)
    assert summary["pipeline"] == "Blocked"
    assert summary["estimate"] == 8.0
    assert summary["priority"] == "High"
    assert summary["workspace_id"] == ctx.workspace_id
    assert "zenhub_url" in summary


def test_issue_cmd_json_includes_pipeline(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zh.cli.state.resolve_context", lambda **_: make_ctx())
    monkeypatch.setattr(
        "zh.commands.issues.gh_issue_view",
        lambda *_a, **_k: {
            "title": "Libs",
            "body": "body",
            "state": "OPEN",
            "url": "https://github.com/acme/widgets/issues/42",
            "comments": [],
        },
    )
    monkeypatch.setattr(
        "zh.commands.issues.issue_zenhub_summary",
        lambda *_a, **_k: {
            "pipeline": "Blocked",
            "estimate": 8.0,
            "priority": "High",
            "zenhub_url": "https://app.zenhub.com/workspaces/ws/issues/gh/acme/widgets/42",
            "workspace_id": "ws-gid-backend",
        },
    )
    monkeypatch.setattr(
        "zh.commands.issues.list_sub_issues",
        lambda *_a, **_k: {"children": []},
    )
    result = runner.invoke(app, ["-r", "acme/widgets", "issue", "42", "--json"])
    assert result.exit_code == 0, result.output
    assert '"pipeline": "Blocked"' in result.output
    assert '"estimate": 8.0' in result.output
    assert '"zenhub_url"' in result.output



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
