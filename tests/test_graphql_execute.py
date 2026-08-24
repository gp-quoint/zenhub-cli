"""Tests for GraphQL execute helpers and response path walking."""

from __future__ import annotations

import pytest

import zh.api as zh_api
from zh.api import RepoContext, ZhApiError
from zh.json_helpers import data_get, gql_get


def _ctx() -> RepoContext:
    return RepoContext("acme/widgets", "repo-1", "ws-1", "tok")


def test_data_get_and_gql_get() -> None:
    data = {"moveIssue": {"issue": {"number": 7}}}
    assert data_get(data, "moveIssue", "issue", "number") == 7
    assert data_get(data, "missing") is None
    assert gql_get({"data": data}, "moveIssue", "issue", "number") == 7
    assert gql_get({"data": None}, "x") is None


def test_execute_returns_data_and_raises_on_errors(monkeypatch) -> None:
    ctx = _ctx()
    monkeypatch.setattr(ctx, "query", lambda *_a, **_k: {"data": {"ok": True}})
    assert ctx.execute("query { x }", context="t") == {"ok": True}

    monkeypatch.setattr(
        ctx,
        "query",
        lambda *_a, **_k: {"data": None, "errors": [{"message": "boom"}]},
    )
    with pytest.raises(ZhApiError, match="t: GraphQL errors: boom"):
        ctx.execute("query { x }", context="t")


def test_execute_routes_through_query_patch(monkeypatch) -> None:
    """Patches on ``ctx.query`` must still affect ``execute``."""
    ctx = _ctx()
    calls: list[tuple[str, object]] = []

    def _query(query: str, variables=None):
        calls.append((query, variables))
        return {"data": {"n": 1}}

    monkeypatch.setattr(ctx, "query", _query)
    assert ctx.execute("query { n }", {"a": 1}, context="n") == {"n": 1}
    assert calls == [("query { n }", {"a": 1})]


def test_execute_path(monkeypatch) -> None:
    ctx = _ctx()
    monkeypatch.setattr(
        ctx,
        "query",
        lambda *_a, **_k: {"data": {"issueByInfo": {"number": 42}}},
    )
    assert ctx.execute_path("q", {}, "issueByInfo", "number", context="x") == 42
    assert ctx.execute_path("q", {}, "missing", context="x") is None


def test_graphql_execute_module_helper(monkeypatch) -> None:
    monkeypatch.setattr(
        zh_api,
        "graphql_request",
        lambda *_a, **_k: {"data": {"repositoriesByGhId": [{"id": "r1"}]}},
    )
    data = zh_api.graphql_execute("query { x }", {}, token="t", context="c")
    assert data == {"repositoriesByGhId": [{"id": "r1"}]}
