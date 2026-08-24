"""Typed helpers for parsing GraphQL JSON responses."""

from __future__ import annotations

from typing import cast

from zh.types import JsonDict, JsonValue

_EMPTY: JsonDict = {}


def as_dict(value: object) -> JsonDict:
    return cast(JsonDict, value) if isinstance(value, dict) else _EMPTY


def as_list(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def dict_nodes(value: object) -> list[JsonDict]:
    return [cast(JsonDict, item) for item in as_list(value) if isinstance(item, dict)]


def gql_data(resp: JsonDict) -> JsonDict:
    return as_dict(resp.get("data"))


def data_get(data: object, *keys: str) -> JsonValue:
    """Walk *keys* through an already-extracted GraphQL ``data`` object."""
    node: object = data
    for key in keys:
        node = as_dict(node).get(key)
    return node


def gql_get(resp: JsonDict, *keys: str) -> JsonValue:
    """Walk *keys* under ``resp["data"]`` (full GraphQL envelope)."""
    return data_get(gql_data(resp), *keys)


def json_int(value: object, default: int = 0) -> int:
    """Coerce a JSON value to int (bools rejected)."""
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def json_str(value: object, default: str = "") -> str:
    """Coerce a JSON value to str."""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return default


def json_str_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = json_str(value)
    return text if text else None
