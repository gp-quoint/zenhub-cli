"""Tests for GraphQL read caching (L1 process + L2 diskcache)."""

from __future__ import annotations

import pytest

import zh.api
from zh.graphql_cache import (
    bump_graphql_cache_gen,
    clear_process_read_cache,
    close_disk_cache,
    is_graphql_mutation,
    parse_ttl_seconds,
)
from zh.graphql_helpers import PageInfo, paginate_pages


def test_is_graphql_mutation() -> None:
    assert is_graphql_mutation("mutation { x }")
    assert not is_graphql_mutation("query { x }")


def test_parse_ttl_seconds() -> None:
    assert parse_ttl_seconds("5m") == 300
    assert parse_ttl_seconds("300") == 300
    assert parse_ttl_seconds("1h") == 3600
    assert parse_ttl_seconds("30s") == 30


def test_graphql_request_uses_process_read_cache(monkeypatch) -> None:
    monkeypatch.setenv("ZH_GRAPHQL_CACHE", "0")
    clear_process_read_cache()
    calls = 0

    def _direct(query, variables=None, *, token, timeout=30.0, url=zh.api.ZH_GRAPHQL_URL):
        nonlocal calls
        calls += 1
        return {"data": {"ok": True}}

    monkeypatch.setattr(zh.api, "_graphql_request_direct", _direct)

    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")
    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")

    assert calls == 1


def test_graphql_request_skips_cache_for_mutations(monkeypatch) -> None:
    monkeypatch.setenv("ZH_GRAPHQL_CACHE", "0")
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


def test_mutation_invalidates_process_read_cache(monkeypatch) -> None:
    monkeypatch.setenv("ZH_GRAPHQL_CACHE", "0")
    clear_process_read_cache()
    calls = 0

    def _direct(query, variables=None, *, token, timeout=30.0, url=zh.api.ZH_GRAPHQL_URL):
        nonlocal calls
        calls += 1
        return {"data": {"ok": True}}

    monkeypatch.setattr(zh.api, "_graphql_request_direct", _direct)

    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")
    zh.api.graphql_request("mutation { x }", {}, token="tok")
    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")

    assert calls == 3


def test_disk_cache_hit_across_process_clear(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ZH_GRAPHQL_CACHE", "1")
    monkeypatch.setenv("ZH_GRAPHQL_CACHE_DIR", str(tmp_path / "gql"))
    monkeypatch.delenv("ZH_GRAPHQL_CACHE_FORCE", raising=False)
    clear_process_read_cache()
    close_disk_cache()
    calls = 0

    def _direct(query, variables=None, *, token, timeout=30.0, url=zh.api.ZH_GRAPHQL_URL):
        nonlocal calls
        calls += 1
        return {"data": {"ok": True, "n": calls}}

    monkeypatch.setattr(zh.api, "_graphql_request_direct", _direct)

    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")
    assert calls == 1

    clear_process_read_cache()
    close_disk_cache()

    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")
    assert calls == 1


def test_mutation_bumps_disk_gen(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ZH_GRAPHQL_CACHE", "1")
    monkeypatch.setenv("ZH_GRAPHQL_CACHE_DIR", str(tmp_path / "gql"))
    monkeypatch.delenv("ZH_GRAPHQL_CACHE_FORCE", raising=False)
    clear_process_read_cache()
    close_disk_cache()
    calls = 0

    def _direct(query, variables=None, *, token, timeout=30.0, url=zh.api.ZH_GRAPHQL_URL):
        nonlocal calls
        calls += 1
        return {"data": {"ok": True, "n": calls}}

    monkeypatch.setattr(zh.api, "_graphql_request_direct", _direct)

    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")
    assert calls == 1
    clear_process_read_cache()
    close_disk_cache()

    zh.api.graphql_request("mutation { x }", {}, token="tok")
    assert calls == 2
    clear_process_read_cache()
    close_disk_cache()

    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")
    assert calls == 3


def test_force_skips_disk_read(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ZH_GRAPHQL_CACHE", "1")
    monkeypatch.setenv("ZH_GRAPHQL_CACHE_DIR", str(tmp_path / "gql"))
    monkeypatch.delenv("ZH_GRAPHQL_CACHE_FORCE", raising=False)
    clear_process_read_cache()
    close_disk_cache()
    calls = 0

    def _direct(query, variables=None, *, token, timeout=30.0, url=zh.api.ZH_GRAPHQL_URL):
        nonlocal calls
        calls += 1
        return {"data": {"ok": True, "n": calls}}

    monkeypatch.setattr(zh.api, "_graphql_request_direct", _direct)

    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")
    assert calls == 1
    clear_process_read_cache()
    close_disk_cache()

    monkeypatch.setenv("ZH_GRAPHQL_CACHE_FORCE", "1")
    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")
    assert calls == 2


def test_bump_gen_increments(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ZH_GRAPHQL_CACHE", "1")
    monkeypatch.setenv("ZH_GRAPHQL_CACHE_DIR", str(tmp_path / "gql"))
    close_disk_cache()
    assert bump_graphql_cache_gen() == 1
    assert bump_graphql_cache_gen() == 2


def test_disk_cache_readonly_falls_back_to_process(monkeypatch, tmp_path) -> None:
    """Readonly L2 must not crash; L1 process cache still works."""
    import zh.graphql_cache as gc

    monkeypatch.setenv("ZH_GRAPHQL_CACHE", "1")
    monkeypatch.setenv("ZH_GRAPHQL_CACHE_DIR", str(tmp_path / "gql"))
    monkeypatch.delenv("ZH_GRAPHQL_CACHE_FORCE", raising=False)
    clear_process_read_cache()
    close_disk_cache()
    calls = 0

    def _direct(query, variables=None, *, token, timeout=30.0, url=zh.api.ZH_GRAPHQL_URL):
        nonlocal calls
        calls += 1
        return {"data": {"ok": True, "n": calls}}

    monkeypatch.setattr(zh.api, "_graphql_request_direct", _direct)

    class BoomCache:
        def __init__(self, *_a, **_k):
            raise OSError("attempt to write a readonly database")

    monkeypatch.setattr(gc, "Cache", BoomCache)

    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")
    zh.api.graphql_request("query { viewer { id } }", {}, token="tok")
    assert calls == 1
    assert bump_graphql_cache_gen() == 0


def test_paginate_pages_stops_on_stuck_cursor() -> None:
    calls = 0

    def fetch(after: str | None) -> tuple[list[int], PageInfo]:
        nonlocal calls
        calls += 1
        return [calls], {"hasNextPage": True, "endCursor": "same"}

    items, warning = paginate_pages(fetch, max_pages=10)
    assert items == [1, 2]
    assert warning is not None
    assert "not advancing" in warning
    assert calls == 2


def test_paginate_pages_respects_cap() -> None:
    def fetch(after: str | None) -> tuple[list[int], PageInfo]:
        return [1], {"hasNextPage": True, "endCursor": f"c-{after}"}

    items, warning = paginate_pages(fetch, max_pages=3)
    assert len(items) == 3
    assert warning is not None
    assert "cap" in warning


def test_graphql_execute_raises_on_errors(monkeypatch) -> None:
    monkeypatch.setenv("ZH_GRAPHQL_CACHE", "0")

    def _direct(query, variables=None, *, token, timeout=30.0, url=zh.api.ZH_GRAPHQL_URL):
        return {"data": None, "errors": [{"message": "boom"}]}

    monkeypatch.setattr(zh.api, "_graphql_request_direct", _direct)
    with pytest.raises(zh.api.ZhApiError, match=r"demo: GraphQL errors: boom"):
        zh.api.graphql_execute("query { x }", {}, token="tok", context="demo")
