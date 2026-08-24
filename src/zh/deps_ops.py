"""Issue dependency (block / unblock) operations."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from zh._http import urlopen_https
from zh.api import RepoContext, ZhApiError, check_graphql_errors, get_gh_repo_id, load_config, resolve_rest_token
from zh.issue_ops import parse_issue_number
from zh.json_helpers import as_dict, gql_get
from zh.schemas import BlockageResult

ZH_REST_URL = "https://api.zenhub.com/p1/dependencies"

_BLOCK_PAIR_QUERY = """
query($repoId: ID!, $num1: Int!, $num2: Int!) {
  blocked: issueByInfo(repositoryId: $repoId, issueNumber: $num1) { id title }
  blocking: issueByInfo(repositoryId: $repoId, issueNumber: $num2) { id title }
}
"""

_CREATE_BLOCKAGE = """
mutation($input: CreateBlockageInput!) {
  createBlockage(input: $input) { blockage { id } }
}
"""


def create_blockage(ctx: RepoContext, blocked_number: int, blocking_number: int) -> BlockageResult:
    """Make *blocked_number* depend on *blocking_number*."""
    resp = ctx.query(
        _BLOCK_PAIR_QUERY,
        {"repoId": ctx.repo_id, "num1": blocked_number, "num2": blocking_number},
    )
    check_graphql_errors(resp, context="block pair lookup")
    blocked = as_dict(gql_get(resp, "blocked"))
    blocking = as_dict(gql_get(resp, "blocking"))
    blocked_id = blocked.get("id")
    blocking_id = blocking.get("id")
    if not blocked_id:
        raise ZhApiError(f"Issue #{blocked_number} not found")
    if not blocking_id:
        raise ZhApiError(f"Issue #{blocking_number} not found")
    mut = ctx.query(
        _CREATE_BLOCKAGE,
        {
            "input": {
                "blocked": {"id": blocked_id, "type": "ISSUE"},
                "blocking": {"id": blocking_id, "type": "ISSUE"},
            },
        },
    )
    check_graphql_errors(mut, context="createBlockage")
    blockage_id = as_dict(as_dict(gql_get(mut, "createBlockage")).get("blockage")).get("id")
    if not blockage_id:
        raise ZhApiError("Failed to create blockage")
    return {
        "blocked": str(blocked_number),
        "blocked_title": str(blocked.get("title") or ""),
        "blocking": str(blocking_number),
        "blocking_title": str(blocking.get("title") or ""),
    }


def _raise_for_rest_status(code: int, body: str, *, blocked: int, blocking: int) -> None:
    match code:
        case 200 | 204:
            return
        case 401:
            raise ZhApiError(
                "Authentication failed. Check your ZH_REST_TOKEN.\nGenerate at: https://app.zenhub.com/dashboard/tokens",
            )
        case 404:
            raise ZhApiError(f"Dependency not found between #{blocked} and #{blocking}")
        case _:
            raise ZhApiError(f"Failed to remove dependency (HTTP {code}): {body}")


def remove_blockage(owner_repo: str, blocked_raw: str, blocking_raw: str) -> None:
    """Remove a dependency via the ZenHub REST API (requires ``ZH_REST_TOKEN``)."""
    blocked_num = parse_issue_number(blocked_raw)
    blocking_num = parse_issue_number(blocking_raw)
    token = resolve_rest_token(load_config())
    gh_repo_id = get_gh_repo_id(owner_repo)
    payload = {
        "blocking": {"repo_id": gh_repo_id, "issue_number": blocking_num},
        "blocked": {"repo_id": gh_repo_id, "issue_number": blocked_num},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ZH_REST_URL,
        data=data,
        headers={
            "X-Authentication-Token": token,
            "Content-Type": "application/json",
        },
        method="DELETE",
    )
    try:
        with urlopen_https(req, timeout=30.0) as resp:
            code = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        code = exc.code
        body = exc.read().decode("utf-8", errors="replace")
        try:
            _raise_for_rest_status(code, body, blocked=blocked_num, blocking=blocking_num)
        except ZhApiError as err:
            raise err from exc
    except urllib.error.URLError as exc:
        raise ZhApiError(f"Transport error removing dependency: {exc.reason}") from exc
    _raise_for_rest_status(code, body, blocked=blocked_num, blocking=blocking_num)
