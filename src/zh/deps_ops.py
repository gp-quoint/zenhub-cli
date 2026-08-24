"""Issue dependency (block / unblock) operations."""

from __future__ import annotations

from zh._http import request_text
from zh.api import RepoContext, ZhApiError, get_gh_repo_id, load_config, resolve_rest_token
from zh.issue_ops import parse_issue_number
from zh.json_helpers import as_dict, data_get
from zh.operations import op
from zh.schemas import BlockageResult

ZH_REST_URL = "https://api.zenhub.com/p1/dependencies"

_BLOCK_PAIR_QUERY = op("deps", "BlockPair")

_CREATE_BLOCKAGE = op("deps", "CreateBlockage")


def create_blockage(ctx: RepoContext, blocked_number: int, blocking_number: int) -> BlockageResult:
    """Make *blocked_number* depend on *blocking_number*."""
    data = ctx.execute(
        _BLOCK_PAIR_QUERY,
        {"repoId": ctx.repo_id, "num1": blocked_number, "num2": blocking_number},
        context="block pair lookup",
    )
    blocked = as_dict(data_get(data, "blocked"))
    blocking = as_dict(data_get(data, "blocking"))
    blocked_id = blocked.get("id")
    blocking_id = blocking.get("id")
    if not blocked_id:
        raise ZhApiError(f"Issue #{blocked_number} not found")
    if not blocking_id:
        raise ZhApiError(f"Issue #{blocking_number} not found")
    data = ctx.execute(
        _CREATE_BLOCKAGE,
        {
            "input": {
                "blocked": {"id": blocked_id, "type": "ISSUE"},
                "blocking": {"id": blocking_id, "type": "ISSUE"},
            },
        },
        context="createBlockage",
    )
    blockage_id = as_dict(as_dict(data_get(data, "createBlockage")).get("blockage")).get("id")
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
    code, body = request_text(
        "DELETE",
        ZH_REST_URL,
        headers={
            "X-Authentication-Token": token,
            "Content-Type": "application/json",
        },
        json_body=payload,
        timeout=30.0,
    )
    _raise_for_rest_status(code, body, blocked=blocked_num, blocking=blocking_num)
