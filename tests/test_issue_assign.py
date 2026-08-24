"""Python tests for assign / unassign safety."""

from __future__ import annotations

import pytest
from tests._fixtures import make_ctx, patch_ctx_query

from zh.issue_ops import assign_issue, unassign_issue


def _issue_resp(assignees: list[dict[str, str]]) -> dict:
    return {
        "data": {
            "issueByInfo": {
                "id": "iid",
                "title": "T",
                "assignees": {"nodes": assignees},
            },
        },
    }


def _ws_resp(users: list[dict[str, str]]) -> dict:
    return {"data": {"workspace": {"assignees": {"nodes": users}}}}


def test_unassign_named_user_removes_only_that_user() -> None:
    ctx = make_ctx()
    with patch_ctx_query(
        ctx,
        [
            _issue_resp(
                [
                    {"id": "uid-daniel", "login": "daniel-pittman"},
                    {"id": "uid-alina", "login": "alinavalshchuk"},
                ],
            ),
            {"data": {"removeAssigneesFromIssues": {"successCount": 1, "githubErrors": None}}},
            _issue_resp([{"id": "uid-alina", "login": "alinavalshchuk"}]),
        ],
    ):
        captured: list[dict] = []
        orig = ctx.execute

        def _spy(query, variables=None, **kwargs):
            if "removeAssigneesFromIssues" in query:
                captured.append(variables)
            return orig(query, variables, **kwargs)

        ctx.execute = _spy  # type: ignore[method-assign]
        result = unassign_issue(ctx, 882, ["daniel-pittman"])
    assert captured[0]["input"]["assigneeIds"] == ["uid-daniel"]
    assert result["assignees"] == ["alinavalshchuk"]


def test_unassign_no_target_refuses_to_clear_all() -> None:
    ctx = make_ctx()
    with patch_ctx_query(ctx, [_issue_resp([])]):
        with pytest.raises(Exception, match="Refusing to remove all assignees"):
            unassign_issue(ctx, 882, [])


def test_unassign_all_flag_clears_everyone() -> None:
    ctx = make_ctx()
    with patch_ctx_query(
        ctx,
        [
            _issue_resp(
                [
                    {"id": "uid-daniel", "login": "daniel-pittman"},
                    {"id": "uid-alina", "login": "alinavalshchuk"},
                ],
            ),
            {"data": {"removeAssigneesFromIssues": {"successCount": 1, "githubErrors": None}}},
            _issue_resp([]),
        ],
    ):
        captured: list[dict] = []
        orig = ctx.execute

        def _spy(query, variables=None, **kwargs):
            if "removeAssigneesFromIssues" in query:
                captured.append(variables)
            return orig(query, variables, **kwargs)

        ctx.execute = _spy  # type: ignore[method-assign]
        unassign_issue(ctx, 882, [], clear_all=True)
    assert set(captured[0]["input"]["assigneeIds"]) == {"uid-daniel", "uid-alina"}


def test_assign_multiple_users() -> None:
    ctx = make_ctx()
    with patch_ctx_query(
        ctx,
        [
            _issue_resp([]),
            _ws_resp([{"id": "uid-alice", "login": "alice"}, {"id": "uid-bob", "login": "bob"}]),
            {"data": {"addAssigneesToIssues": {"successCount": 2, "githubErrors": None}}},
            _issue_resp([{"id": "uid-alice", "login": "alice"}, {"id": "uid-bob", "login": "bob"}]),
        ],
    ):
        captured: list[dict] = []
        orig = ctx.execute

        def _spy(query, variables=None, **kwargs):
            if "addAssigneesToIssues" in query:
                captured.append(variables)
            return orig(query, variables, **kwargs)

        ctx.execute = _spy  # type: ignore[method-assign]
        result = assign_issue(ctx, 882, ["alice", "bob"])
    assert set(captured[0]["input"]["assigneeIds"]) == {"uid-alice", "uid-bob"}
    assert result["assignees"] == ["alice", "bob"]
