"""Tests for workspace GraphQL reads (pipelines, labels, pipeline issues)."""

from __future__ import annotations

from unittest.mock import patch

import zh.api
from zh.workspace_ops import pipeline_issues


def _ctx() -> zh.api.RepoContext:
    return zh.api.RepoContext(
        owner_repo="acme/widgets",
        repo_id="repo-gid-123",
        workspace_id="workspace-gid-456",
        token="fake-token",
    )


def _pipelines_response() -> dict:
    return {
        "data": {
            "workspace": {
                "name": "Backend Team",
                "pipelinesConnection": {
                    "nodes": [{"id": "pipe-1", "name": "New Issues", "issues": {"totalCount": 1}}],
                },
            }
        }
    }


def _pipeline_issues_response() -> dict:
    return {
        "data": {
            "searchIssuesByPipeline": {
                "nodes": [
                    {
                        "number": 42,
                        "title": "Fix login",
                        "estimate": {"value": 3},
                        "assignees": {"nodes": [{"login": "alice"}]},
                        "repository": {"ownerName": "acme", "name": "widgets"},
                        "zenhubUrl": "https://app.zenhub.com/workspaces/w/issues/42",
                    }
                ]
            }
        }
    }


def test_pipeline_issues_uses_empty_filters_by_default() -> None:
    ctx = _ctx()
    captured: list[dict] = []

    def _query(query: str, variables: dict | None = None) -> dict:
        captured.append(variables or {})
        if "pipelinesConnection" in query:
            return _pipelines_response()
        return _pipeline_issues_response()

    with patch.object(ctx, "query", side_effect=_query):
        result = pipeline_issues(ctx, "New Issues", pipeline_id="pipe-1")

    assert result["pipeline"] == "New Issues"
    assert len(result["issues"]) == 1
    issue_filters = captured[-1]["filters"]
    assert issue_filters == {}
    assert "states" not in issue_filters


def test_pipeline_issues_assignee_filter_uses_in_shape() -> None:
    ctx = _ctx()
    captured: list[dict] = []

    def _query(query: str, variables: dict | None = None) -> dict:
        captured.append(variables or {})
        if "pipelinesConnection" in query:
            return _pipelines_response()
        return _pipeline_issues_response()

    with patch.object(ctx, "query", side_effect=_query):
        pipeline_issues(ctx, "New Issues", assignee="@alice", pipeline_id="pipe-1")

    issue_filters = captured[-1]["filters"]
    assert issue_filters == {"assignees": {"in": ["alice"]}}
