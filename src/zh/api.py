"""Direct ZenHub GraphQL client (httpx).

Auth and repo/workspace resolution mirror ``~/.config/zh/config``.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import cast

from zh._http import request_json
from zh.errors import ZhApiError
from zh.graphql_cache import (
    cached_graphql_read,
    clear_process_read_cache,
    close_disk_cache,
    invalidate_graphql_read_caches,
    is_graphql_mutation,
)
from zh.graphql_helpers import PageInfo, paginate_pages
from zh.json_helpers import as_dict, as_list, data_get, dict_nodes
from zh.operations import op
from zh.schemas import WorkspaceRow
from zh.types import GraphQLVariables, JsonDict, JsonValue

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "zh" / "config"
ZH_GRAPHQL_URL = "https://api.zenhub.com/public/graphql"

_CONFIG_KEY_RE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$")


_MIN_WRAPPED_QUOTE_LEN = 2


def _strip_quotes(s: str) -> str:
    """Strip a single layer of surrounding quotes if present."""
    if len(s) >= _MIN_WRAPPED_QUOTE_LEN and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1]
    return s


def load_config(config_path: Path | str | None = None) -> dict[str, str]:
    """Read ~/.config/zh/config into a dict.

    Mirrors the bash `source` semantics conservatively: KEY=value pairs,
    lines starting with `#` are comments, surrounding quotes are stripped.
    Env-var-style export prefixes (`export KEY=value`) are accepted.

    Args:
        config_path: Optional override. Falls back to DEFAULT_CONFIG_PATH.

    Returns:
        Dict of config values. Missing file returns {} (caller decides
        whether absence is fatal).
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if config_path is None:
        return _load_default_config()
    return _read_config_file(path)


@lru_cache(maxsize=1)
def _load_default_config() -> dict[str, str]:
    return _read_config_file(DEFAULT_CONFIG_PATH)


def _read_config_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        m = _CONFIG_KEY_RE.match(line)
        if not m:
            continue
        out[m.group(1)] = _strip_quotes(m.group(2))
    return out


def resolve_rest_token(config: dict[str, str] | None = None) -> str:
    """Resolve the ZenHub REST token (required for ``unblock`` only)."""
    if env_token := os.environ.get("ZH_REST_TOKEN", "").strip():
        return env_token
    if config is None:
        config = load_config()
    token = config.get("ZH_REST_TOKEN", "").strip()
    if not token:
        raise ZhApiError(
            "REST API token required for unblock command.\n"
            "The ZenHub GraphQL API does not support removing dependencies.\n"
            "Generate a token at: https://app.zenhub.com/dashboard/tokens\n"
            "Add to ~/.config/zh/config:\n  ZH_REST_TOKEN=your_token_here",
        )
    return token


def resolve_token(config: dict[str, str] | None = None) -> str:
    """Resolve the ZenHub GraphQL token.

    Priority: ZH_TOKEN env var > config file. Raises ZhApiError if absent
    (or empty), since every GraphQL call needs it.
    """
    if env_token := os.environ.get("ZH_TOKEN", "").strip():
        return env_token
    if config is None:
        config = load_config()
    token = config.get("ZH_TOKEN", "").strip()
    if not token:
        raise ZhApiError(
            "ZH_TOKEN not set. Create ~/.config/zh/config with:\n  ZH_TOKEN=your_graphql_token\nGenerate at: https://app.zenhub.com/settings/tokens"
        )
    return token


def graphql_request(
    query: str,
    variables: GraphQLVariables | None = None,
    *,
    token: str | None = None,
    timeout: float = 30.0,
    url: str = ZH_GRAPHQL_URL,
) -> JsonDict:
    """Send a GraphQL request and return the parsed JSON response.

    Read-only queries use an in-process memo (L1) and, unless disabled, a
    ``diskcache`` on-disk store (L2; see ``ZH_GRAPHQL_CACHE*``). Mutations
    always hit the network and invalidate caches so the next ``zh pipeline``
    / ``zh sprint`` sees fresh membership.
    """
    if token is None:
        token = resolve_token()
    if is_graphql_mutation(query):
        result = _graphql_request_direct(query, variables, token=token, timeout=timeout, url=url)
        invalidate_graphql_read_caches()
        return result
    return cached_graphql_read(
        query,
        variables,
        token=token,
        timeout=timeout,
        url=url,
        direct_request=_graphql_request_direct,
    )


def _graphql_request_direct(
    query: str,
    variables: GraphQLVariables | None = None,
    *,
    token: str,
    timeout: float = 30.0,
    url: str = ZH_GRAPHQL_URL,
) -> JsonDict:
    """Send a GraphQL request without read caches."""
    payload: JsonDict = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    result = request_json(
        "POST",
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json_body=payload,
        timeout=timeout,
    )
    if not isinstance(result, dict):
        raise ZhApiError(f"Unexpected GraphQL JSON shape from ZenHub: {type(result).__name__}")
    return cast(JsonDict, result)


def check_graphql_errors(response: JsonDict, *, context: str = "") -> None:
    """Raise ZhApiError if the GraphQL response has top-level `errors`.

    GraphQL allows partial-data responses where `data` is populated and
    `errors` is present. For mutations and structural queries the MCP
    relies on, we treat any top-level error as fatal.
    """
    errors = as_list(response.get("errors"))
    if errors:
        msg = "; ".join(str(as_dict(e).get("message") or e) for e in errors if isinstance(e, dict))
        prefix = f"{context}: " if context else ""
        raise ZhApiError(f"{prefix}GraphQL errors: {msg or errors}")


def graphql_execute(
    query: str,
    variables: GraphQLVariables | None = None,
    *,
    token: str | None = None,
    timeout: float = 30.0,
    url: str = ZH_GRAPHQL_URL,
    context: str = "",
) -> JsonDict:
    """Send a GraphQL request, raise on top-level errors, return ``data``."""
    resp = graphql_request(query, variables, token=token, timeout=timeout, url=url)
    check_graphql_errors(resp, context=context)
    data = resp.get("data")
    return cast(JsonDict, data) if isinstance(data, dict) else {}


_GH_URL_RE = re.compile(
    # dots allowed in repo names; ^ anchor rejects garbage prefixes (lockstep with similarity.py)
    r"^(?:git@github\.com:|https?://github\.com/)"
    r"(?P<owner>[^/]+)/"
    r"(?P<repo>[^/]+?)(?:\.git)?/?$"
)


def get_owner_repo_from_git(cwd: str | os.PathLike[str] | None = None) -> str:
    """Resolve `owner/repo` from the cwd's git origin remote.

    Raises ZhApiError if not a git repo, no origin remote, or origin URL
    doesn't parse as a GitHub URL.
    """
    try:
        out = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise ZhApiError(
            "Could not determine repository from git remote. "
            "Run this MCP tool with an explicit repo_path that points to "
            "a git checkout with a GitHub remote, or pass owner_repo "
            "directly to the underlying helper."
        ) from e

    m = _GH_URL_RE.search(out)
    if not m:
        raise ZhApiError(f"Origin remote URL did not parse as GitHub URL: {out!r}")
    return f"{m.group('owner')}/{m.group('repo')}"


@lru_cache(maxsize=1)
def _default_gh_token() -> str:
    try:
        return subprocess.check_output(["gh", "auth", "token"], text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise ZhApiError("Could not get GitHub token via `gh auth token`. Either authenticate the gh CLI or pass gh_token explicitly.") from e


def get_gh_repo_id(owner_repo: str, *, gh_token: str | None = None) -> int:
    """Get the GitHub numeric repo ID via the GitHub REST API.

    Used as the input to ZenHub's `repositoryByGhId` / `repositoriesByGhId`
    queries.
    """
    if gh_token is not None:
        return _fetch_gh_repo_id(owner_repo, gh_token)
    return _cached_gh_repo_id(owner_repo.casefold())


@lru_cache(maxsize=32)
def _cached_gh_repo_id(owner_repo_key: str) -> int:
    owner, _, repo = owner_repo_key.partition("/")
    if not repo:
        msg = f"Invalid owner/repo: {owner_repo_key!r}"
        raise ZhApiError(msg)
    return _fetch_gh_repo_id(f"{owner}/{repo}", _default_gh_token())


def _fetch_gh_repo_id(owner_repo: str, gh_token: str) -> int:
    url = f"https://api.github.com/repos/{owner_repo}"
    body = request_json(
        "GET",
        url,
        headers={
            "Authorization": f"token {gh_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15.0,
    )
    if not isinstance(body, dict):
        raise ZhApiError(f"GitHub API returned non-object JSON for repos/{owner_repo}")
    repo_id = cast(JsonDict, body).get("id")
    if not isinstance(repo_id, int):
        raise ZhApiError(f"GitHub API returned no numeric id for repos/{owner_repo}")
    return repo_id


_REPO_ID_QUERY = op("repo", "RepositoriesByGhId")
_WORKSPACE_QUERY = op("repo", "WorkspacesConnection")
_WORKSPACE_PAGINATION_CAP = 50  # 50 pages x 50 nodes


def get_zenhub_repo_id(
    owner_repo: str,
    *,
    gh_id: int | None = None,
    token: str | None = None,
    gh_token: str | None = None,
) -> str:
    """Resolve the ZenHub repository ID for a GitHub `owner/repo`."""
    if token is None:
        token = resolve_token()
    if gh_id is None:
        gh_id = get_gh_repo_id(owner_repo, gh_token=gh_token)
    return _cached_zenhub_repo_id(gh_id, token)


@lru_cache(maxsize=32)
def _cached_zenhub_repo_id(gh_id: int, token: str) -> str:
    data = graphql_execute(_REPO_ID_QUERY, {"ghIds": [gh_id]}, token=token, context="repositoriesByGhId")
    nodes = dict_nodes(data.get("repositoriesByGhId"))
    if not nodes:
        raise ZhApiError(f"No ZenHub repository found for GitHub repo id {gh_id}. Connect the repo to a ZenHub workspace first.")
    repo_id = nodes[0].get("id")
    if not isinstance(repo_id, str) or not repo_id:
        raise ZhApiError(f"No ZenHub repository found for GitHub repo id {gh_id}. Connect the repo to a ZenHub workspace first.")
    return repo_id


def list_workspaces(
    owner_repo: str,
    *,
    gh_id: int | None = None,
    token: str | None = None,
    gh_token: str | None = None,
) -> list[WorkspaceRow]:
    """Return every workspace this repo is connected to."""
    if token is None:
        token = resolve_token()
    if gh_id is None:
        gh_id = get_gh_repo_id(owner_repo, gh_token=gh_token)
    return [{"id": row[0], "name": row[1] or ""} for row in _cached_workspaces(gh_id, token)]


@lru_cache(maxsize=32)
def _cached_workspaces(gh_id: int, token: str) -> tuple[tuple[str, str | None], ...]:
    repository_found = False

    def fetch_page(after: str | None) -> tuple[list[WorkspaceRow], PageInfo]:
        nonlocal repository_found
        data = graphql_execute(
            _WORKSPACE_QUERY,
            {"ghIds": [gh_id], "after": after},
            token=token,
            context="workspacesConnection",
        )
        repos = as_list(data.get("repositoriesByGhId"))
        if not repos:
            return [], {}
        repository_found = True
        conn = as_dict(as_dict(repos[0]).get("workspacesConnection"))
        return [cast(WorkspaceRow, node) for node in dict_nodes(conn.get("nodes"))], cast(PageInfo, as_dict(conn.get("pageInfo")))

    out, _warning = paginate_pages(fetch_page, max_pages=_WORKSPACE_PAGINATION_CAP)
    if not repository_found:
        raise ZhApiError(f"No ZenHub repository found for GitHub repo id {gh_id}")

    return tuple((str(row.get("id") or ""), row.get("name")) for row in out)


def get_workspace_id(
    owner_repo: str,
    *,
    gh_id: int | None = None,
    workspace_name: str | None = None,
    token: str | None = None,
    gh_token: str | None = None,
) -> str:
    """Resolve the ZenHub workspace ID for a repo."""
    nodes = list_workspaces(owner_repo, gh_id=gh_id, token=token, gh_token=gh_token)
    if not nodes:
        raise ZhApiError(f"No workspace found for {owner_repo}")

    if workspace_name:
        want = workspace_name.lower()
        for n in nodes:
            if (n.get("name") or "").lower() == want:
                return str(n["id"])
        available = ", ".join(n.get("name") or "?" for n in nodes)
        raise ZhApiError(f"Workspace {workspace_name!r} not found for {owner_repo}. Available: {available}")
    return str(nodes[0]["id"])


def repos_match(a: JsonDict | dict[str, object] | None, owner_repo: str) -> bool:
    """Case-insensitive ``repository`` node vs ``owner/repo``."""
    if not a:
        return False
    owner, _, repo = owner_repo.partition("/")
    return str(a.get("ownerName") or "").lower() == owner.lower() and str(a.get("name") or "").lower() == repo.lower()


@dataclass
class RepoContext:
    """Resolved repo + workspace identifiers and an authenticated query helper."""

    owner_repo: str
    repo_id: str
    workspace_id: str
    token: str

    def query(self, query: str, variables: GraphQLVariables | None = None) -> JsonDict:
        """Return the full GraphQL envelope (``data`` + optional ``errors``)."""
        return graphql_request(query, variables, token=self.token)

    def execute(
        self,
        query: str,
        variables: GraphQLVariables | None = None,
        *,
        context: str = "",
    ) -> JsonDict:
        """POST, raise on GraphQL errors, return ``data`` (or ``{}``).

        Routes through :meth:`query` so tests that patch ``ctx.query`` keep working.
        """
        response = self.query(query, variables)
        check_graphql_errors(response, context=context)
        return as_dict(response.get("data"))

    def execute_path(
        self,
        query: str,
        variables: GraphQLVariables | None,
        *keys: str,
        context: str = "",
    ) -> JsonValue:
        """Like ``execute``, then walk ``data`` by ``keys`` (missing → None)."""
        data = self.execute(query, variables, context=context)
        if not keys:
            return data
        return data_get(data, *keys)


def resolve_context(
    cwd: str | os.PathLike[str] | None = None,
    *,
    owner_repo: str | None = None,
    workspace_name: str | None = None,
    config: dict[str, str] | None = None,
) -> RepoContext:
    """Resolve owner_repo, repo_id, workspace_id, and token.

    Repo precedence: arg > ZH_REPO_OVERRIDE > ZH_REPO/config > git remote.
    Workspace precedence: arg > ZH_WORKSPACE_NAME > ZH_WORKSPACE/config > first.
    Matches bash ``zh`` flag/env resolution.
    """
    if config is None:
        config = load_config()
    token = resolve_token(config)

    if owner_repo is None:
        owner_repo = (
            os.environ.get("ZH_REPO_OVERRIDE", "").strip() or os.environ.get("ZH_REPO", "").strip() or config.get("ZH_REPO", "").strip() or None
        )
    if owner_repo is None:
        owner_repo = get_owner_repo_from_git(cwd=cwd)

    if workspace_name is None:
        workspace_name = (
            os.environ.get("ZH_WORKSPACE_NAME", "").strip()
            or os.environ.get("ZH_WORKSPACE", "").strip()
            or config.get("ZH_WORKSPACE", "").strip()
            or None
        )

    gh_id = get_gh_repo_id(owner_repo)
    repo_id = get_zenhub_repo_id(owner_repo, gh_id=gh_id, token=token)
    workspace_id = get_workspace_id(owner_repo, gh_id=gh_id, workspace_name=workspace_name, token=token)
    return RepoContext(owner_repo, repo_id, workspace_id, token)


def clear_api_caches() -> None:
    """Drop in-process resolution and config caches (tests)."""
    _load_default_config.cache_clear()
    _default_gh_token.cache_clear()
    _cached_gh_repo_id.cache_clear()
    _cached_zenhub_repo_id.cache_clear()
    _cached_workspaces.cache_clear()
    clear_process_read_cache()
    close_disk_cache()
