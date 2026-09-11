"""Tests for GraphQL operation document loading."""

from __future__ import annotations

import pytest

from zh.errors import ZhApiError
from zh.operations import clear_operations_cache, op


@pytest.fixture(autouse=True)
def _clear_ops_cache() -> None:
    clear_operations_cache()
    yield
    clear_operations_cache()


def test_op_loads_issue_pipeline_includes_deps() -> None:
    src = op("issues", "IssuePipeline")
    assert "blockingIssues" in src
    assert "blockedIssues" in src


def test_op_loads_named_issue_by_info() -> None:
    src = op("issues", "IssueByInfo")
    assert src.startswith("query IssueByInfo")
    assert "issueByInfo(repositoryId: $repoId" in src
    assert "parentIssue" in src


def test_op_loads_mutation() -> None:
    src = op("issues", "MoveIssue")
    assert src.startswith("mutation MoveIssue")
    assert "moveIssue(input: $input)" in src


def test_op_unknown_name() -> None:
    with pytest.raises(ZhApiError, match="Unknown GraphQL operation"):
        op("issues", "DoesNotExist")


def test_op_unknown_document() -> None:
    with pytest.raises(ZhApiError, match="not found"):
        op("nope", "Anything")


def test_documents_cover_hot_paths() -> None:
    expected = {
        "repo": ["RepositoriesByGhId", "WorkspacesConnection"],
        "issues": ["IssueByInfo", "CreateIssue", "MoveIssue"],
        "workspace": ["PipelinesOpen", "SearchIssuesByPipeline"],
        "subissues": ["ListSubIssues", "AddSubIssues"],
        "sprints": ["SprintsOpen", "SprintIssuesPage", "AddIssuesToSprints"],
        "deps": ["BlockPair", "CreateBlockage"],
        "planning": ["ListByIssueType", "HierarchyChildrenDetail"],
    }
    for document, names in expected.items():
        for name in names:
            body = op(document, name)
            assert name in body.split("(", 1)[0]
