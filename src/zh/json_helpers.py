"""Typed helpers for parsing GraphQL JSON responses."""

from __future__ import annotations

from typing import Any, cast

from zh.api import JsonDict

_EMPTY: JsonDict = {}


def as_dict(value: Any) -> JsonDict:
    return cast(JsonDict, value) if isinstance(value, dict) else _EMPTY


def as_list(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def dict_nodes(value: Any) -> list[JsonDict]:
    return [cast(JsonDict, item) for item in as_list(value) if isinstance(item, dict)]


def gql_data(resp: JsonDict) -> JsonDict:
    return as_dict(resp.get("data"))


def gql_get(resp: JsonDict, *keys: str) -> Any:
    node: Any = gql_data(resp)
    for key in keys:
        node = as_dict(node).get(key)
    return node
