"""Tests for GraphQL read caching."""

from __future__ import annotations

from unittest.mock import patch

import zh.api
from zh.graphql_cache import (
    bkt_enabled,
    clear_process_read_cache,
    is_graphql_mutation,
)


def test_is_graphql_mutation() -> None:
    assert is_graphql_mutation("mutation { x }")
    assert not is_graphql_mutation("query { x }")


def test_graphql_request_uses_process_read_cache(monkeypatch) -> None:
    clear_process_read_cache()
    calls = 0

    def _direct(query, variables=None, *, token, timeout=30.0, url=zh.api.ZH_GRAPHQL_URL):
        nonlocal calls
        calls += 1
        return {"data": {"ok": True}}

    monkeypatch.setattr("zh.graphql_cache.bkt_enabled", lambda: False)
    monkeypatch.setattr(zh.api, "_graphql_request_direct", _direct)

    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")
    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")

    assert calls == 1


def test_graphql_request_skips_cache_for_mutations(monkeypatch) -> None:
    clear_process_read_cache()
    calls = 0

    def _direct(query, variables=None, *, token, timeout=30.0, url=zh.api.ZH_GRAPHQL_URL):
        nonlocal calls
        calls += 1
        return {"data": {"ok": True}}

    monkeypatch.setattr(zh.api, "_graphql_request_direct", _direct)

    zh.api.graphql_request("mutation { x }", {}, token="tok")
    zh.api.graphql_request("mutation { x }", {}, token="tok")

    assert calls == 2


def test_bkt_disabled_when_zh_bkt_zero(monkeypatch) -> None:
    monkeypatch.setenv("ZH_BKT", "0")
    assert bkt_enabled() is False
