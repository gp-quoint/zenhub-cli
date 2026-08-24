"""GraphQL read caching: in-process L1 + diskcache L2."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

from diskcache import Cache  # type: ignore[import-untyped]

from zh.errors import ZhApiError
from zh.types import GraphQLVariables, JsonDict

_MUTATION_RE = re.compile(r"^\s*mutation\b", re.I)
_PROCESS_READ_CACHE: dict[str, JsonDict] = {}
_GEN_KEY = "__zh_graphql_cache_gen__"
_DEFAULT_TTL = "5m"

# Mutable holder avoids ``global`` statements for the open Cache handle.
_DISK: dict[str, Cache | Path | None] = {"cache": None, "dir": None}


def is_graphql_mutation(query: str) -> bool:
    return bool(_MUTATION_RE.match(query or ""))


def disk_cache_enabled() -> bool:
    return os.environ.get("ZH_GRAPHQL_CACHE", "").strip() != "0"


def disk_cache_force() -> bool:
    return os.environ.get("ZH_GRAPHQL_CACHE_FORCE", "").strip() == "1"


def parse_ttl_seconds(raw: str | None = None) -> int:
    """Parse ``5m`` / ``300`` / ``1h`` style TTL into seconds (default 300)."""
    text = (raw if raw is not None else os.environ.get("ZH_GRAPHQL_CACHE_TTL", "")).strip() or _DEFAULT_TTL
    if text.isdigit():
        return max(1, int(text))
    m = re.fullmatch(r"(\d+)([smhd])", text, re.I)
    if not m:
        raise ZhApiError(f"Invalid ZH_GRAPHQL_CACHE_TTL: {text!r} (use e.g. 5m, 300, 1h)")
    n = int(m.group(1))
    unit = m.group(2).lower()
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return max(1, n * mult)


def graphql_cache_dir() -> Path:
    override = os.environ.get("ZH_GRAPHQL_CACHE_DIR", "").strip()
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    root = Path(xdg) if xdg else Path.home() / ".cache"
    return root / "zh" / "graphql"


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _open_disk_cache() -> Cache:
    path = graphql_cache_dir()
    existing = _DISK["cache"]
    if isinstance(existing, Cache) and _DISK["dir"] == path:
        return existing
    if isinstance(existing, Cache):
        existing.close()
    path.mkdir(parents=True, exist_ok=True)
    cache = Cache(str(path))
    _DISK["cache"] = cache
    _DISK["dir"] = path
    return cache


def close_disk_cache() -> None:
    """Close the diskcache handle (tests / shutdown)."""
    existing = _DISK["cache"]
    if isinstance(existing, Cache):
        existing.close()
    _DISK["cache"] = None
    _DISK["dir"] = None


def _current_gen(cache: Cache) -> int:
    value = cast(object, cache.get(_GEN_KEY, default=0))  # type: ignore[reportUnknownMemberType]
    try:
        return int(value or 0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def bump_graphql_cache_gen() -> int:
    """Bump the disk-cache generation so subsequent L2 keys miss."""
    if not disk_cache_enabled():
        return 0
    cache = _open_disk_cache()
    nxt = _current_gen(cache) + 1
    cache.set(_GEN_KEY, nxt)  # type: ignore[reportUnknownMemberType]
    return nxt


def _make_cache_key(query: str, variables: GraphQLVariables | None, token: str, gen: int) -> str:
    payload = json.dumps(
        {"q": query, "v": variables or {}, "t": _token_fingerprint(token), "g": gen},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cached_graphql_read(
    query: str,
    variables: GraphQLVariables | None,
    *,
    token: str,
    timeout: float,
    url: str,
    direct_request: Callable[..., JsonDict],
) -> JsonDict:
    """Return a GraphQL read response via L1 process memo and optional L2 diskcache."""
    force = disk_cache_force()
    gen = 0
    disk: Cache | None = None
    if disk_cache_enabled() and not force:
        disk = _open_disk_cache()
        gen = _current_gen(disk)

    key = _make_cache_key(query, variables, token, gen)

    cached = _PROCESS_READ_CACHE.get(key)
    if cached is not None:
        return cached

    if disk is not None:
        hit = cast(object, disk.get(key, default=None))  # type: ignore[reportUnknownMemberType]
        if isinstance(hit, dict):
            cached_hit = cast(JsonDict, hit)
            _PROCESS_READ_CACHE[key] = cached_hit
            return cached_hit

    result = direct_request(query, variables, token=token, timeout=timeout, url=url)
    _PROCESS_READ_CACHE[key] = result

    if disk_cache_enabled() and not force:
        if disk is None:
            disk = _open_disk_cache()
        disk.set(key, result, expire=parse_ttl_seconds())  # type: ignore[reportUnknownMemberType]

    return result


def invalidate_graphql_read_caches() -> None:
    """Drop L1 and bump L2 generation after mutations."""
    clear_process_read_cache()
    bump_graphql_cache_gen()


def clear_process_read_cache() -> None:
    """Drop in-process GraphQL read entries."""
    _PROCESS_READ_CACHE.clear()
