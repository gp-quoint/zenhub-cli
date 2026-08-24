"""GraphQL read caching: in-process memo + optional ``bkt`` subprocess cache."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from zh._http import assert_https_url
from zh.errors import ZhApiError

type JsonDict = dict[str, Any]

_MUTATION_RE = re.compile(r"^\s*mutation\b", re.I)
_PROCESS_READ_CACHE: dict[tuple[str, str, str], JsonDict] = {}


def is_graphql_mutation(query: str) -> bool:
    return bool(_MUTATION_RE.match(query or ""))


def bkt_enabled() -> bool:
    if os.environ.get("ZH_BKT", "").strip() == "0":
        return False
    return shutil.which("bkt") is not None


def bkt_ttl() -> str:
    return os.environ.get("ZH_BKT_TTL", "").strip() or "5m"


def bkt_force() -> bool:
    return os.environ.get("ZH_BKT_FORCE", "").strip() == "1"


def graphql_cache_gen_path() -> Path:
    """File whose mtime is part of the ``bkt`` cache key (bumped on mutations)."""
    override = os.environ.get("ZH_GRAPHQL_CACHE_GEN", "").strip()
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    root = Path(xdg) if xdg else Path.home() / ".cache"
    return root / "zh" / "graphql-cache.gen"


def ensure_graphql_cache_gen_file() -> Path:
    path = graphql_cache_gen_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("0\n", encoding="utf-8")
    return path


def bump_graphql_cache_gen() -> None:
    """Touch the gen file so subsequent ``bkt`` reads miss stale entries."""
    path = ensure_graphql_cache_gen_file()
    try:
        current = int(path.read_text(encoding="utf-8").strip() or "0")
    except ValueError:
        current = 0
    path.write_text(f"{current + 1}\n", encoding="utf-8")


def invalidate_graphql_read_caches() -> None:
    """Drop in-process reads and invalidate the cross-invocation ``bkt`` scope."""
    clear_process_read_cache()
    bump_graphql_cache_gen()


def _read_cache_key(query: str, variables: dict[str, Any] | None, token: str) -> tuple[str, str, str]:
    return (query, json.dumps(variables or {}, sort_keys=True), token)


def _graphql_via_bkt(
    query: str,
    variables: dict[str, Any] | None,
    *,
    token: str,
    timeout: float,
    url: str,
) -> JsonDict:
    assert_https_url(url)
    gen_file = ensure_graphql_cache_gen_file()
    payload_str = json.dumps({"query": query, "variables": variables or {}})
    curl_cmd = [
        "curl",
        "-sfS",
        "-X",
        "POST",
        url,
        "-H",
        f"Authorization: Bearer {token}",
        "-H",
        "Content-Type: application/json",
        "-d",
        payload_str,
    ]
    bkt_cmd = [
        "bkt",
        "--scope",
        "zh-graphql",
        "--ttl",
        bkt_ttl(),
        "--discard-failures",
        "--env",
        "ZH_TOKEN",
        "--modtime",
        str(gen_file),
        *([] if not bkt_force() else ["--force"]),
        "--",
        *curl_cmd,
    ]
    env = {**os.environ, "ZH_TOKEN": token}
    try:
        proc = subprocess.run(
            bkt_cmd,
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ZhApiError(f"Transport error to ZenHub GraphQL: bkt timed out after {timeout}s") from exc
    except OSError as exc:
        raise ZhApiError(f"Transport error to ZenHub GraphQL: {exc}") from exc

    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip() or proc.stdout.decode("utf-8", errors="replace").strip()
        raise ZhApiError(f"HTTP error from ZenHub GraphQL via bkt: {detail or proc.returncode}")

    body = proc.stdout.decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ZhApiError(f"Non-JSON response from ZenHub: {body[:200]!r}") from exc


def cached_graphql_read(
    query: str,
    variables: dict[str, Any] | None,
    *,
    token: str,
    timeout: float,
    url: str,
    direct_request,
) -> JsonDict:
    """Return a GraphQL read response, using process and optional bkt caches."""
    key = _read_cache_key(query, variables, token)
    cached = _PROCESS_READ_CACHE.get(key)
    if cached is not None:
        return cached

    if bkt_enabled():
        result = _graphql_via_bkt(query, variables, token=token, timeout=timeout, url=url)
    else:
        result = direct_request(query, variables, token=token, timeout=timeout, url=url)

    _PROCESS_READ_CACHE[key] = result
    return result


def clear_process_read_cache() -> None:
    """Drop in-process GraphQL read entries."""
    _PROCESS_READ_CACHE.clear()
