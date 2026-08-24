"""ZenHub GraphQL: sub-issues, sprints, and related mutations.

Uses RepoContext from zh.api; returns native Python structures. With
replaceParent unset, addSubIssues rejects children on another parent via
failedIssues (no symmetric pre-flight on add; remove keeps pre-flight).
"""

from __future__ import annotations

from typing import Any, cast

from zh.api import (
    RepoContext,
    ZhApiError,
    repos_match,
)
from zh.graphql_helpers import (
    PageInfo,
    finalize_child_mutation_payload,
    paginate_pages,
    parse_sprint_issue_node,
    parse_subissue_child_node,
    remove_subissue_preflight_failure_payload,
)
from zh.json_helpers import as_dict, data_get, dict_nodes
from zh.operations import op
from zh.schemas import (
    IssueInfo,
    MutationResult,
    SprintDetailResult,
    SprintListResult,
    SubIssueListResult,
)


_ISSUE_BY_INFO_QUERY = op("issues", "IssueByInfo")


def _is_positive_int(n) -> bool:
    """Reject bool — isinstance(n, int) is true for bool in Python."""
    return isinstance(n, int) and not isinstance(n, bool) and n > 0


def get_issue_by_info(ctx: RepoContext, issue_number: int) -> IssueInfo | None:
    """Fetch a single issue's structural info via the context's query method.

    Returns None when the issue doesn't exist in this repository. Raises
    ZhApiError for bad input or top-level GraphQL errors.
    """
    if not _is_positive_int(issue_number):
        raise ZhApiError(f"issue number must be a positive int (got {issue_number!r})")
    raw = ctx.execute_path(
        _ISSUE_BY_INFO_QUERY,
        {"repoId": ctx.repo_id, "issueNumber": issue_number},
        "issueByInfo",
        context="issueByInfo",
    )
    return cast(IssueInfo, raw) if raw is not None else None


MAX_PAGINATION_ITERATIONS = 200
_GRAPHQL_PAGE_SIZE = 100


_SUBISSUE_LIST_QUERY = op("subissues", "ListSubIssues")


def _subissue_list_not_found(parent_number: int) -> SubIssueListResult:
    return {
        "ok": False,
        "parent_number": parent_number,
        "parent_title": "",
        "parent_state": None,
        "total_count": 0,
        "fetched_count": 0,
        "children": [],
        "pagination_warning": None,
        "error": f"Issue #{parent_number} not found in this repository",
    }


def _walk_subissue_children(
    ctx: RepoContext,
    parent_number: int,
) -> tuple[list[dict], str, str | None, int, str | None, SubIssueListResult | None]:
    parent_title = ""
    parent_state: str | None = None
    total_count = 0
    first_page = True
    not_found = False

    def fetch_page(after: str | None) -> tuple[list[dict], PageInfo]:
        nonlocal first_page, not_found, parent_state, parent_title, total_count
        issue = as_dict(
            ctx.execute_path(
                _SUBISSUE_LIST_QUERY,
                {
                    "repoId": ctx.repo_id,
                    "issueNumber": parent_number,
                    "workspaceId": ctx.workspace_id,
                    "after": after,
                },
                "issueByInfo",
                context="list_sub_issues",
            ),
        )
        if not issue:
            not_found = True
            return [], {}
        if first_page:
            parent_title = str(issue.get("title") or "")
            parent_state = issue.get("state")
            total_count = int(as_dict(issue.get("githubChildIssues")).get("totalCount") or 0)
            first_page = False
        conn = as_dict(issue.get("githubChildIssues"))
        children = [parse_subissue_child_node(node) for node in dict_nodes(conn.get("nodes"))]
        return children, cast(PageInfo, as_dict(conn.get("pageInfo")))

    children, pagination_warning = paginate_pages(
        fetch_page,
        max_pages=MAX_PAGINATION_ITERATIONS,
    )
    if not_found:
        return children, parent_title, parent_state, total_count, pagination_warning, _subissue_list_not_found(parent_number)
    return children, parent_title, parent_state, total_count, pagination_warning, None


def list_sub_issues(ctx: RepoContext, parent_number: int) -> SubIssueListResult:
    """List sub-issues of a parent (paginated)."""
    if not _is_positive_int(parent_number):
        raise ZhApiError(f"parent_number must be a positive int (got {parent_number!r})")

    children, parent_title, parent_state, total_count, pagination_warning, not_found = _walk_subissue_children(
        ctx,
        parent_number,
    )
    if not_found is not None:
        return not_found

    return {
        "ok": True,
        "parent_number": parent_number,
        "parent_title": parent_title,
        "parent_state": parent_state,
        "total_count": total_count,
        "fetched_count": len(children),
        "children": children,
        "pagination_warning": pagination_warning,
    }


_ADD_SUB_ISSUES_MUTATION = op("subissues", "AddSubIssues")

_REMOVE_SUB_ISSUES_MUTATION = op("subissues", "RemoveSubIssues")


def _resolve_child_id(ctx: RepoContext, child_number: int) -> dict:
    """Look up a child issue's GraphQL id + its current parent (if any)."""
    if not _is_positive_int(child_number):
        raise ZhApiError(f"child issue number must be a positive int (got {child_number!r})")
    issue = get_issue_by_info(ctx, child_number)
    if not issue:
        return {"ok": False, "child_number": child_number, "error": "not found"}
    return {"ok": True, "child_number": child_number, "issue": issue}


def _classify_outcome(success_count: int, failed_count: int) -> str:
    """Map (success, failed) counts to outcome keyword."""
    if failed_count > 0 and success_count > 0:
        return "partial"
    if failed_count > 0:
        return "fail"
    if success_count == 0:
        return "noop"
    return "ok"


def add_sub_issues(ctx: RepoContext, parent_number: int, child_numbers: list[int]) -> MutationResult:
    """Link children under parent; wrong-parent rejects surface in failedIssues."""
    if not child_numbers:
        raise ZhApiError("child_numbers must be non-empty")
    for n in child_numbers:
        if not _is_positive_int(n):
            raise ZhApiError(f"every child number must be a positive int (got {n!r})")

    child_numbers = list(dict.fromkeys(child_numbers))

    parent_issue = get_issue_by_info(ctx, parent_number)
    if not parent_issue:
        return {
            "ok": False,
            "parent_number": parent_number,
            "outcome": "fail",
            "success_count": 0,
            "failed_count": 0,
            "succeeded": [],
            "failed": [],
            "unaccounted": list(child_numbers),
            "failed_unknown_count": 0,
            "github_errors": None,
            "partial_success_warning": None,
            "error": f"Parent #{parent_number} not found in this repository",
        }
    parent_id = parent_issue["id"]

    child_ids: list[str] = []
    not_found: list[int] = []
    for n in child_numbers:
        info = _resolve_child_id(ctx, n)
        if not info["ok"]:
            not_found.append(n)
        else:
            child_ids.append(info["issue"]["id"])
    if not_found:
        not_found_set = set(not_found)
        return {
            "ok": False,
            "parent_number": parent_number,
            "outcome": "fail",
            "success_count": 0,
            "failed_count": len(not_found),
            "succeeded": [],
            "failed": [{"number": n, "owner": "", "name": ""} for n in not_found],
            "unaccounted": [n for n in child_numbers if n not in not_found_set],
            "failed_unknown_count": 0,
            "github_errors": None,
            "partial_success_warning": None,
            "error": ("Some child issue numbers were not found in this repository: " + ", ".join(f"#{n}" for n in not_found)),
        }

    data = ctx.execute(
        _ADD_SUB_ISSUES_MUTATION,
        {"input": {"parentId": parent_id, "childIssueIds": child_ids}},
        context="addSubIssues",
    )
    payload = as_dict(data_get(data, "addSubIssues"))
    return finalize_child_mutation_payload(
        child_numbers=child_numbers,
        parent_number=parent_number,
        payload=payload,
        classify_outcome=_classify_outcome,
    )


def _validate_remove_sub_issues_children(
    ctx: RepoContext,
    parent_number: int,
    child_numbers: list[int],
) -> tuple[MutationResult | None, str | None, list[dict]]:
    parent_issue = get_issue_by_info(ctx, parent_number)
    if not parent_issue:
        return (
            {
                "ok": False,
                "parent_number": parent_number,
                "outcome": "fail",
                "success_count": 0,
                "failed_count": 0,
                "succeeded": [],
                "failed": [],
                "unaccounted": list(child_numbers),
                "failed_unknown_count": 0,
                "github_errors": None,
                "partial_success_warning": None,
                "error": f"Parent #{parent_number} not found in this repository",
            },
            None,
            [],
        )

    resolved: list[dict] = []
    not_found: list[int] = []
    wrong_parent: list[dict] = []
    cross_repo: list[dict] = []

    for n in child_numbers:
        info = _resolve_child_id(ctx, n)
        if not info["ok"]:
            not_found.append(n)
            continue
        issue = info["issue"]
        if not repos_match(issue.get("repository"), ctx.owner_repo):
            cross_repo.append(
                {
                    "number": n,
                    "owner": (issue.get("repository") or {}).get("ownerName") or "",
                    "name": (issue.get("repository") or {}).get("name") or "",
                }
            )
            continue
        actual_parent = issue.get("parentIssue") or None
        if not actual_parent or actual_parent.get("number") != parent_number:
            wrong_parent.append(
                {
                    "number": n,
                    "actual_parent": (actual_parent.get("number") if actual_parent else None),
                }
            )
            continue
        resolved.append(issue)

    if not_found or wrong_parent or cross_repo:
        return (
            remove_subissue_preflight_failure_payload(
                parent_number=parent_number,
                child_numbers=child_numbers,
                not_found=not_found,
                cross_repo=cross_repo,
                wrong_parent=wrong_parent,
            ),
            None,
            [],
        )

    return None, parent_issue["id"], resolved


def remove_sub_issues(ctx: RepoContext, parent_number: int, child_numbers: list[int]) -> MutationResult:
    """Unlink each child from its parent.

    The API's `removeSubIssues` only takes child IDs — it unlinks each
    from its actual parent. We do a pre-flight check that each child
    actually has `parent_number` as its parent in the cwd's repo, to
    catch wrong-parent typos.

    Returns the same shape as `add_sub_issues` with `succeeded` listing
    the children actually unlinked.

    Duplicate input numbers are collapsed first-occurrence (matches
    `add_sub_issues` and the sprint mutations).
    """
    if not child_numbers:
        raise ZhApiError("child_numbers must be non-empty")
    for n in child_numbers:
        if not _is_positive_int(n):
            raise ZhApiError(f"every child number must be a positive int (got {n!r})")

    child_numbers = list(dict.fromkeys(child_numbers))

    preflight_error, parent_id, resolved = _validate_remove_sub_issues_children(ctx, parent_number, child_numbers)
    if preflight_error is not None:
        return preflight_error

    child_ids = [issue["id"] for issue in resolved]

    data = ctx.execute(
        _REMOVE_SUB_ISSUES_MUTATION,
        {"input": {"parentId": parent_id, "childIssueIds": child_ids}},
        context="removeSubIssues",
    )
    payload = as_dict(data_get(data, "removeSubIssues"))
    return finalize_child_mutation_payload(
        child_numbers=child_numbers,
        parent_number=parent_number,
        payload=payload,
        classify_outcome=_classify_outcome,
    )


_REPRIORITIZE_SUB_ISSUE_MUTATION = op("subissues", "ReprioritizeSubIssue")


def _reorder_sub_issue_result(
    *,
    ok: bool,
    child_number: int,
    parent_number: int | None,
    position: str,
    outcome: str,
    error: str | None,
) -> MutationResult:
    return {
        "ok": ok,
        "child_number": child_number,
        "parent_number": parent_number,
        "position": position,
        "outcome": outcome,
        "error": error,
    }


def _normalize_reorder_position(position: str, sibling_number: int | None) -> str:
    pos = (position or "").lower().strip()
    if pos in {"top", "first"}:
        return "top"
    if pos in {"bottom", "last"}:
        return "bottom"
    if pos in {"after", "before"}:
        if not _is_positive_int(sibling_number):
            raise ZhApiError(f"position {pos!r} requires a positive sibling_number (got {sibling_number!r})")
        return pos
    raise ZhApiError(f"position must be one of top/bottom/after/before (got {position!r})")


def _find_sibling_id_by_number_in_repo(
    siblings: list[dict[str, Any]],
    num: int,
    owner_repo: str,
) -> str | None:
    for s in siblings:
        if s.get("number") != num:
            continue
        rep = s.get("repository") or {}
        if repos_match(
            {"ownerName": rep.get("owner"), "name": rep.get("name")},
            owner_repo,
        ):
            return s.get("id")
    return None


def _resolve_top_bottom_reorder_anchor(
    *,
    pos: str,
    siblings: list[dict[str, Any]],
    child_id: str,
    child_number: int,
    parent_number: int,
) -> tuple[str | None, str | None, str, MutationResult | None]:
    if pos == "top":
        other = next(
            (s for s in siblings if s.get("id") and s.get("id") != child_id),
            None,
        )
        if other is None:
            return (
                None,
                None,
                "top",
                _reorder_sub_issue_result(
                    ok=False,
                    child_number=child_number,
                    parent_number=parent_number,
                    position="top",
                    outcome="noop",
                    error=(f"#{child_number} is the only sub-issue of #{parent_number} — nothing to reorder against"),
                ),
            )
        return None, other.get("id"), "top", None

    last_other = None
    for s in reversed(siblings):
        if s.get("id") and s.get("id") != child_id:
            last_other = s
            break
    if last_other is None:
        return (
            None,
            None,
            "bottom",
            _reorder_sub_issue_result(
                ok=False,
                child_number=child_number,
                parent_number=parent_number,
                position="bottom",
                outcome="noop",
                error=(f"#{child_number} is the only sub-issue of #{parent_number} — nothing to reorder against"),
            ),
        )
    return last_other.get("id"), None, "bottom", None


def _resolve_relative_reorder_anchor(
    *,
    pos: str,
    ctx: RepoContext,
    siblings: list[dict[str, Any]],
    sibling_number: int | None,
    child_number: int,
    parent_number: int,
) -> tuple[str | None, str | None, str, MutationResult | None]:
    position_desc = f"{pos} #{sibling_number}"
    sib_id = _find_sibling_id_by_number_in_repo(siblings, sibling_number, ctx.owner_repo)
    if not sib_id:
        return (
            None,
            None,
            position_desc,
            _reorder_sub_issue_result(
                ok=False,
                child_number=child_number,
                parent_number=parent_number,
                position=position_desc,
                outcome="fail",
                error=(f"Anchor #{sibling_number} not found among sub-issues of #{parent_number} in {ctx.owner_repo}"),
            ),
        )
    if pos == "after":
        return sib_id, None, position_desc, None
    return None, sib_id, position_desc, None


def _resolve_reorder_anchors(
    *,
    ctx: RepoContext,
    pos: str,
    siblings: list[dict[str, Any]],
    child_id: str,
    child_number: int,
    parent_number: int,
    sibling_number: int | None,
) -> tuple[str | None, str | None, str, MutationResult | None]:
    if pos in {"top", "bottom"}:
        after_id, before_id, position_desc, error = _resolve_top_bottom_reorder_anchor(
            pos=pos,
            siblings=siblings,
            child_id=child_id,
            child_number=child_number,
            parent_number=parent_number,
        )
    else:
        after_id, before_id, position_desc, error = _resolve_relative_reorder_anchor(
            pos=pos,
            ctx=ctx,
            siblings=siblings,
            sibling_number=sibling_number,
            child_number=child_number,
            parent_number=parent_number,
        )
    if error is not None:
        return after_id, before_id, position_desc, error

    if after_id is None and before_id is None:
        return (
            after_id,
            before_id,
            position_desc,
            _reorder_sub_issue_result(
                ok=False,
                child_number=child_number,
                parent_number=parent_number,
                position=position_desc,
                outcome="fail",
                error=("Internal: no anchor resolved (both afterId and beforeId are null). Refusing to fire a vacuous reorder."),
            ),
        )

    return after_id, before_id, position_desc, None


def _resolve_reorder_child_context(
    ctx: RepoContext,
    child_number: int,
    pos: str,
) -> tuple[MutationResult | None, int, str, str]:
    child_issue = get_issue_by_info(ctx, child_number)
    if not child_issue:
        return (
            _reorder_sub_issue_result(
                ok=False,
                child_number=child_number,
                parent_number=None,
                position=pos,
                outcome="fail",
                error=f"Child #{child_number} not found in this repository",
            ),
            0,
            "",
            "",
        )
    parent_info = child_issue.get("parentIssue") or None
    if not parent_info:
        return (
            _reorder_sub_issue_result(
                ok=False,
                child_number=child_number,
                parent_number=None,
                position=pos,
                outcome="fail",
                error=f"#{child_number} is not currently a sub-issue of any parent",
            ),
            0,
            "",
            "",
        )
    return None, parent_info.get("number"), parent_info.get("id"), child_issue.get("id")


def _load_reorder_siblings(
    ctx: RepoContext,
    *,
    parent_number: int,
    child_number: int,
    pos: str,
) -> tuple[MutationResult | None, list[dict[str, Any]]]:
    sibling_listing = list_sub_issues(ctx, parent_number)
    if not sibling_listing.get("ok"):
        return (
            _reorder_sub_issue_result(
                ok=False,
                child_number=child_number,
                parent_number=parent_number,
                position=pos,
                outcome="fail",
                error=sibling_listing.get("error") or "Could not list siblings",
            ),
            [],
        )
    sibling_pagination_warning = sibling_listing.get("pagination_warning")
    if sibling_pagination_warning and pos in {"top", "bottom"}:
        return (
            _reorder_sub_issue_result(
                ok=False,
                child_number=child_number,
                parent_number=parent_number,
                position=pos,
                outcome="fail",
                error=(
                    f"Cannot determine sibling order for '{pos}' under "
                    f"partial pagination — sub-issue listing bailed: "
                    f"{sibling_pagination_warning}. Re-list "
                    f"('zh subissue list #{parent_number}') and retry "
                    f"once full coverage is available, OR use 'after' / "
                    f"'before' with an explicit sibling number."
                ),
            ),
            [],
        )
    return None, sibling_listing.get("children") or []


def _execute_reorder_sub_issue_mutation(
    ctx: RepoContext,
    *,
    parent_id: str,
    child_id: str,
    after_id: str | None,
    before_id: str | None,
    child_number: int,
    parent_number: int,
    position_desc: str,
) -> MutationResult:
    data = ctx.execute(
        _REPRIORITIZE_SUB_ISSUE_MUTATION,
        {
            "input": {
                "parentId": parent_id,
                "childIssueId": child_id,
                "afterId": after_id,
                "beforeId": before_id,
            }
        },
        context="reprioritizeSubIssue",
    )
    payload = as_dict(data_get(data, "reprioritizeSubIssue"))
    success = bool(payload.get("success"))
    github_errors = payload.get("githubErrors") or None
    if isinstance(github_errors, dict) and not github_errors:
        github_errors = None

    if not success:
        return _reorder_sub_issue_result(
            ok=False,
            child_number=child_number,
            parent_number=parent_number,
            position=position_desc,
            outcome="fail",
            error=f"API rejected reorder; githubErrors={github_errors}",
        )
    return _reorder_sub_issue_result(
        ok=True,
        child_number=child_number,
        parent_number=parent_number,
        position=position_desc,
        outcome="ok",
        error=None,
    )


def reorder_sub_issue(
    ctx: RepoContext,
    child_number: int,
    position: str,
    sibling_number: int | None = None,
) -> MutationResult:
    """Reorder a sub-issue among its parent's children.

    Position keywords:
      - "top" / "first"   — first sibling
      - "bottom" / "last" — last sibling
      - "after"           — requires sibling_number; right after sibling
      - "before"          — requires sibling_number; right before sibling

    Returns:
        dict with:
            ok: bool — true iff outcome == "ok"
            child_number: int
            parent_number: int | None
            position: str — normalized human-readable
            outcome: "ok"|"noop"|"fail"
            error: str | None
    """
    pos = _normalize_reorder_position(position, sibling_number)

    if not _is_positive_int(child_number):
        raise ZhApiError(f"child_number must be a positive int (got {child_number!r})")
    if pos in {"after", "before"} and sibling_number == child_number:
        raise ZhApiError(f"cannot anchor #{child_number} {pos} itself (self-anchor)")

    child_error, parent_number, parent_id, child_id = _resolve_reorder_child_context(ctx, child_number, pos)
    if child_error is not None:
        return child_error

    sibling_error, siblings = _load_reorder_siblings(
        ctx,
        parent_number=parent_number,
        child_number=child_number,
        pos=pos,
    )
    if sibling_error is not None:
        return sibling_error

    after_id, before_id, position_desc, anchor_error = _resolve_reorder_anchors(
        ctx=ctx,
        pos=pos,
        siblings=siblings,
        child_id=child_id,
        child_number=child_number,
        parent_number=parent_number,
        sibling_number=sibling_number,
    )
    if anchor_error is not None:
        return anchor_error

    return _execute_reorder_sub_issue_mutation(
        ctx,
        parent_id=parent_id,
        child_id=child_id,
        after_id=after_id,
        before_id=before_id,
        child_number=child_number,
        parent_number=parent_number,
        position_desc=position_desc,
    )


_SPRINTS_QUERY_OPEN = op("sprints", "SprintsOpen")

_SPRINTS_QUERY_ALL = op("sprints", "SprintsAll")


def _serialize_sprint(node: dict, *, active_id: str | None) -> dict:
    return {
        "id": node.get("id"),
        "name": node.get("name") or "",
        "state": node.get("state") or "",
        "start_at": node.get("startAt") or None,
        "end_at": node.get("endAt") or None,
        "completed_points": node.get("completedPoints") or 0.0,
        "total_points": node.get("totalPoints") or 0.0,
        "closed_issues_count": node.get("closedIssuesCount") or 0,
        "is_active": bool(active_id) and node.get("id") == active_id,
    }


def _walk_workspace_sprint_nodes(
    ctx: RepoContext,
    query: str,
) -> tuple[str, str | None, list[dict], str | None]:
    workspace_name = ""
    active_id: str | None = None
    first_page = True

    def fetch_page(after: str | None) -> tuple[list[dict], PageInfo]:
        nonlocal active_id, first_page, workspace_name
        ws = as_dict(
            ctx.execute_path(
                query,
                {"workspaceId": ctx.workspace_id, "after": after},
                "workspace",
                context="list_sprints",
            ),
        )
        if not ws:
            raise ZhApiError(f"Workspace {ctx.workspace_id!r} resolved to null (deleted, ACL-revoked, or otherwise inaccessible)")
        if first_page:
            workspace_name = str(ws.get("name") or "")
            active_id = as_dict(ws.get("activeSprint")).get("id")
            first_page = False
        conn = as_dict(ws.get("sprints"))
        return dict_nodes(conn.get("nodes")), cast(PageInfo, as_dict(conn.get("pageInfo")))

    nodes, pagination_warning = paginate_pages(
        fetch_page,
        max_pages=MAX_PAGINATION_ITERATIONS,
        stuck_warning="Sprint pagination cursor not advancing across requests — server likely mis-reporting hasNextPage. Bailing.",
        cap_warning=f"Sprint pagination iteration cap ({MAX_PAGINATION_ITERATIONS}) exceeded — bailing",
    )

    return workspace_name, active_id, nodes, pagination_warning


def list_sprints(ctx: RepoContext, *, include_closed: bool = False) -> SprintListResult:
    """List sprints (paginated). ``include_closed`` adds CLOSED sprints."""
    query = _SPRINTS_QUERY_ALL if include_closed else _SPRINTS_QUERY_OPEN
    workspace_name, active_id, nodes, pagination_warning = _walk_workspace_sprint_nodes(ctx, query)

    return {
        "ok": True,
        "workspace_name": workspace_name,
        "active_sprint_id": active_id,
        "sprints": [_serialize_sprint(n, active_id=active_id) for n in nodes],
        "pagination_warning": pagination_warning,
    }


_SPRINT_HEADER_QUERY = op("sprints", "SprintHeader")

_SPRINT_ISSUES_PAGE_QUERY = op("sprints", "SprintIssuesPage")


def _resolve_active_sprint_id(
    active_id: str | None,
    sprints: list[dict[str, Any]],
) -> tuple[str | None, str | None, str | None]:
    if not active_id:
        return None, None, "No active sprint in this workspace"
    for s in sprints:
        if s.get("id") == active_id:
            return active_id, s.get("name"), None
    return active_id, "", None


def _resolve_sprint_by_name(
    want_lc: str,
    sprints: list[dict[str, Any]],
    *,
    sprint_name: str,
    listing_pagination_warning: str | None,
) -> tuple[str | None, str | None, str | None]:
    for s in sprints:
        if (s.get("name") or "").lower() == want_lc:
            return s.get("id"), s.get("name"), None
    available = ", ".join(s.get("name") or "?" for s in sprints) or "(none)"
    if listing_pagination_warning:
        return (
            None,
            None,
            (
                f"Sprint {sprint_name!r} not found in the first "
                f"{len(sprints)} walked sprints — listing was "
                f"incomplete due to: {listing_pagination_warning}. "
                f"Try re-running, or provide an exact sprint id."
            ),
        )
    return None, None, f"Sprint {sprint_name!r} not found. Available: {available}"


def _find_sprint_id(ctx: RepoContext, sprint_name: str) -> tuple[str | None, str | None, str | None]:
    """Resolve sprint id by name or ``current``/``active``."""
    want = (sprint_name or "").strip()
    if not want:
        return (
            None,
            None,
            "Sprint name must be non-empty (or use 'current' / 'active')",
        )
    listing = list_sprints(ctx, include_closed=True)
    sprints = listing.get("sprints") or []
    active_id = listing.get("active_sprint_id")
    listing_pagination_warning = listing.get("pagination_warning")
    if want.lower() in {"current", "active"}:
        return _resolve_active_sprint_id(active_id, sprints)
    return _resolve_sprint_by_name(
        want.lower(),
        sprints,
        sprint_name=sprint_name,
        listing_pagination_warning=listing_pagination_warning,
    )


_PIPELINES_ORDER_QUERY = op("workspace", "PipelinesOrder")


def _pipeline_board_index(ctx: RepoContext) -> dict[str, int]:
    """Map pipeline name → board column index (left-to-right).

    Soft-fails to {} on any lookup error so callers can still fall
    back to number-only ordering rather than aborting a read that
    already has its issue list (matches bash `zh sprint`, which
    still renders if the pipelines query hiccups).
    """
    try:
        workspace = ctx.execute_path(
            _PIPELINES_ORDER_QUERY,
            {"workspaceId": ctx.workspace_id},
            "workspace",
            context="pipelines_order",
        )
    except Exception:  # noqa: BLE001 — soft-fail to number-only sort
        return {}
    nodes = dict_nodes(as_dict(as_dict(workspace).get("pipelinesConnection")).get("nodes"))
    out: dict[str, int] = {}
    for i, n in enumerate(nodes):
        name = (n or {}).get("name")
        if name:
            out[name] = i
    return out


def _sort_issues_by_pipeline_then_id(ctx: RepoContext, issues: list[dict]) -> list[dict]:
    """Sort issues by board pipeline, then owner/repo, then issue number.

    Matches `zh sprint` / `zh mine`. Issues with no pipeline (or a
    pipeline not in the board) sort after known columns. Repo comes
    before number because issue numbers are per-repository.
    """
    idx = _pipeline_board_index(ctx)

    def _repo_key(issue: dict) -> str:
        rep = issue.get("repository") or {}
        owner = rep.get("owner") or rep.get("ownerName") or ""
        name = rep.get("name") or ""
        return f"{owner}/{name}".lower()

    return sorted(
        issues,
        key=lambda i: (
            idx.get(i.get("pipeline") or "", 9999),
            _repo_key(i),
            i.get("number") if isinstance(i.get("number"), int) else 0,
        ),
    )


def _collect_sprint_issue_page_nodes(
    conn: dict[str, Any],
    *,
    out: list[dict],
    walked_numbers: set[int],
    owner_repo: str,
) -> None:
    for wrapper in conn.get("nodes") or []:
        if wrapper is None:
            continue
        issue = (wrapper or {}).get("issue")
        if issue is None:
            continue
        walked_num = issue.get("number")
        if isinstance(walked_num, int) and not isinstance(walked_num, bool) and repos_match(issue.get("repository"), owner_repo):
            walked_numbers.add(walked_num)
        out.append(parse_sprint_issue_node(issue))


def _walk_sprint_issues(ctx: RepoContext, sprint_id: str) -> tuple[list[dict], set[int], str | None]:
    """Walk all ``sprintIssues`` pages.

    Returns (all issues, repo-filtered walked_numbers, pagination_warning).
    ``walked_numbers`` matches ``ctx.owner_repo`` for partial-coverage
    classification in ``remove_issues_from_sprint``.

    Raises ZhApiError on ``data.node = null`` (not the same as an empty sprint).
    """
    walked_numbers: set[int] = set()

    def fetch_page(after: str | None) -> tuple[list[dict], PageInfo]:
        node = as_dict(
            ctx.execute_path(
                _SPRINT_ISSUES_PAGE_QUERY,
                {
                    "sprintId": sprint_id,
                    "after": after,
                    "workspaceId": ctx.workspace_id,
                },
                "node",
                context="sprint_issues_page",
            ),
        )
        if not node:
            raise ZhApiError(f"Sprint {sprint_id!r} resolved to null in sprintIssues walk (deleted, ACL-revoked, or otherwise inaccessible)")
        conn = as_dict(node.get("sprintIssues"))
        page_items: list[dict] = []
        _collect_sprint_issue_page_nodes(
            conn,
            out=page_items,
            walked_numbers=walked_numbers,
            owner_repo=ctx.owner_repo,
        )
        return page_items, cast(PageInfo, as_dict(conn.get("pageInfo")))

    out, pagination_warning = paginate_pages(
        fetch_page,
        max_pages=MAX_PAGINATION_ITERATIONS,
        stuck_warning="Sprint-issues pagination cursor not advancing — server likely mis-reporting hasNextPage. Bailing.",
        cap_warning=f"Sprint-issues pagination iteration cap ({MAX_PAGINATION_ITERATIONS}) exceeded — bailing",
    )
    return out, walked_numbers, pagination_warning


def get_sprint_detail(ctx: RepoContext, sprint_name: str) -> SprintDetailResult:
    """Sprint header + paginated issues. ``current``/``active`` select the active sprint.

    Raises ZhApiError when workspace or sprint node resolves to null mid-walk.
    """
    sprint_id, actual_name, err = _find_sprint_id(ctx, sprint_name)
    if err or not sprint_id:
        return {
            "ok": False,
            "sprint_id": None,
            "sprint_name": sprint_name,
            "state": None,
            "start_at": None,
            "end_at": None,
            "completed_points": 0.0,
            "total_points": 0.0,
            "closed_issues_count": 0,
            "description": None,
            "issue_count": 0,
            "issues": [],
            "pagination_warning": None,
            "error": err,
        }

    node = as_dict(
        ctx.execute_path(
            _SPRINT_HEADER_QUERY,
            {"sprintId": sprint_id},
            "node",
            context="sprint_header",
        ),
    )

    issues, _walked_numbers, pagination_warning = _walk_sprint_issues(ctx, sprint_id)

    issues = _sort_issues_by_pipeline_then_id(ctx, issues)

    return {
        "ok": True,
        "sprint_id": sprint_id,
        "sprint_name": node.get("name") or actual_name or sprint_name,
        "state": node.get("state") or None,
        "start_at": node.get("startAt") or None,
        "end_at": node.get("endAt") or None,
        "completed_points": node.get("completedPoints") or 0.0,
        "total_points": node.get("totalPoints") or 0.0,
        "closed_issues_count": node.get("closedIssuesCount") or 0,
        "description": node.get("description") or None,
        "issue_count": len(issues),
        "issues": issues,
        "pagination_warning": pagination_warning,
        "error": None,
    }


def get_current_sprint(ctx: RepoContext) -> SprintDetailResult:
    """Convenience wrapper: detail of the workspace's active sprint."""
    return get_sprint_detail(ctx, "current")


_ADD_ISSUES_TO_SPRINTS_MUTATION = op("sprints", "AddIssuesToSprints")

_REMOVE_ISSUES_FROM_SPRINTS_MUTATION = op("sprints", "RemoveIssuesFromSprints")


def _resolve_issue_ids_in_repo(ctx: RepoContext, issue_numbers: list[int]) -> tuple[dict[int, str], list[int]]:
    """Look up GraphQL ids; callers must dedupe issue_numbers first."""
    out: dict[int, str] = {}
    missing: list[int] = []
    for n in issue_numbers:
        info = get_issue_by_info(ctx, n)
        if not info or not info.get("id"):
            missing.append(n)
        else:
            out[n] = info["id"]
    return out, missing


def _succeeded_numbers_from_add_sprint_links(
    returned_links: list[Any],
    *,
    sprint_id: str,
    owner_repo: str,
) -> set[int]:
    succeeded_numbers: set[int] = set()
    for link in returned_links:
        sprint = (link or {}).get("sprint") or {}
        if sprint.get("id") != sprint_id:
            continue
        issue = (link or {}).get("issue") or {}
        if not repos_match(issue.get("repository"), owner_repo):
            continue
        num = issue.get("number")
        if isinstance(num, int):
            succeeded_numbers.add(num)
    return succeeded_numbers


def _attached_from_sprint_issue_nodes(
    nodes: list[dict],
    owner_repo: str,
) -> tuple[set[int], set[int]]:
    attached: set[int] = set()
    walked: set[int] = set()
    for n_link in nodes or []:
        issue = (n_link or {}).get("issue") or {}
        num = issue.get("number")
        if isinstance(num, int) and not isinstance(num, bool):
            walked.add(num)
        if not repos_match(issue.get("repository"), owner_repo):
            continue
        if isinstance(num, int) and not isinstance(num, bool):
            attached.add(num)
    return attached, walked


def _still_attached_from_walked_issues(
    walked: list[dict],
    owner_repo: str,
) -> set[int]:
    still_attached: set[int] = set()
    for w in walked:
        rep = w.get("repository") or {}
        if not repos_match(
            {"ownerName": rep.get("owner"), "name": rep.get("name")},
            owner_repo,
        ):
            continue
        num = w.get("number")
        if isinstance(num, int) and not isinstance(num, bool):
            still_attached.add(num)
    return still_attached


def _missing_target_sprint_anomaly(
    sprint_id: str,
    sprints_after: list[Any],
) -> str:
    if not sprints_after:
        return "Mutation response had an empty `sprints` array; walked sprint directly to determine post-state."
    returned_ids = [(s or {}).get("id") for s in sprints_after if s]
    return (
        f"Mutation response did not include sprint {sprint_id!r} "
        f"in its `sprints` array (got: {returned_ids!r}); "
        "walked sprint directly to determine post-state."
    )


def _sprint_removal_walk_error_result(
    *,
    sprint_id: str,
    actual_sprint_name: str | None,
    sprint_name: str,
    issue_numbers: list[int],
    response_anomaly: str | None,
    error: str,
) -> MutationResult:
    return {
        "ok": False,
        "sprint_id": sprint_id,
        "sprint_name": actual_sprint_name or sprint_name,
        "outcome": "fail",
        "success_count": 0,
        "failed_count": len(issue_numbers),
        "succeeded": [],
        "failed": list(issue_numbers),
        "unaccounted": [],
        "inspected_full": False,
        "pagination_warning": None,
        "response_anomaly": response_anomaly,
        "partial_success_warning": None,
        "error": error,
    }


def _resolve_removal_post_state(
    ctx: RepoContext,
    *,
    sprint_id: str,
    target_sprint: dict[str, Any] | None,
    sprints_after: list[Any],
) -> tuple[set[int], set[int], bool, str | None, str | None]:
    still_attached_numbers: set[int] = set()
    walked_numbers: set[int] = set()
    inspected_full = False
    pagination_warning: str | None = None
    response_anomaly: str | None = None

    if target_sprint is None:
        response_anomaly = _missing_target_sprint_anomaly(sprint_id, sprints_after)
        walked, walked_numbers, walk_warning = _walk_sprint_issues(ctx, sprint_id)
        still_attached_numbers = _still_attached_from_walked_issues(walked, ctx.owner_repo)
        inspected_full = walk_warning is None
        pagination_warning = walk_warning
        return still_attached_numbers, walked_numbers, inspected_full, pagination_warning, response_anomaly

    nodes = ((target_sprint.get("sprintIssues") or {}).get("nodes")) or []
    still_attached_numbers, walked_numbers = _attached_from_sprint_issue_nodes(nodes, ctx.owner_repo)
    if len(nodes) < _GRAPHQL_PAGE_SIZE:
        return still_attached_numbers, walked_numbers, True, pagination_warning, response_anomaly

    walked, walked_numbers, walk_warning = _walk_sprint_issues(ctx, sprint_id)
    still_attached_numbers = _still_attached_from_walked_issues(walked, ctx.owner_repo)
    inspected_full = walk_warning is None
    pagination_warning = walk_warning
    return still_attached_numbers, walked_numbers, inspected_full, pagination_warning, response_anomaly


def _compute_sprint_removal_outcome(
    *,
    inspected_full: bool,
    issue_numbers: list[int],
    still_attached_numbers: set[int],
    walked_numbers: set[int],
    actual_sprint_name: str | None,
    sprint_name: str,
    pagination_warning: str | None,
    response_anomaly: str | None,
) -> tuple[list[int], list[int], str, list[int], str | None]:
    if inspected_full:
        succeeded = [n for n in issue_numbers if n not in still_attached_numbers]
        failed = [n for n in issue_numbers if n in still_attached_numbers]
        outcome = _classify_outcome(len(succeeded), len(failed))
        return succeeded, failed, outcome, [], response_anomaly

    succeeded = [n for n in issue_numbers if n in walked_numbers and n not in still_attached_numbers]
    failed = [n for n in issue_numbers if n in walked_numbers and n in still_attached_numbers]
    accounted_set: set[int] = set(succeeded) | set(failed)
    unaccounted = [n for n in issue_numbers if n not in accounted_set]
    coverage_note = (
        f"Post-state coverage incomplete (inspected_full=False, "
        f"walker bailed: {pagination_warning or 'unknown reason'}); "
        f"verified {len(succeeded)} of {len(issue_numbers)} input(s) "
        f"as removed; "
        f"{len(unaccounted)} input(s) un-verified — the walker "
        f"never reached them, so we cannot say whether the "
        f"mutation took effect. "
        f"Re-verify with `zh sprint show '{actual_sprint_name or sprint_name}'`."
    )
    response_anomaly = f"{response_anomaly} {coverage_note}" if response_anomaly else coverage_note
    outcome = "partial" if succeeded else "fail"
    return succeeded, failed, outcome, unaccounted, response_anomaly


def add_issues_to_sprint(ctx: RepoContext, sprint_name: str, issue_numbers: list[int]) -> MutationResult:
    """Add issues; missing sprintIssues links count as failed."""
    if not issue_numbers:
        raise ZhApiError("issue_numbers must be non-empty")
    for n in issue_numbers:
        if not _is_positive_int(n):
            raise ZhApiError(f"every issue number must be a positive int (got {n!r})")

    issue_numbers = list(dict.fromkeys(issue_numbers))

    sprint_id, actual_sprint_name, err = _find_sprint_id(ctx, sprint_name)
    if err or not sprint_id:
        return {
            "ok": False,
            "sprint_id": None,
            "sprint_name": sprint_name,
            "outcome": "fail",
            "success_count": 0,
            "failed_count": 0,
            "succeeded": [],
            "failed": [],
            "unaccounted": list(issue_numbers),
            "partial_success_warning": None,
            "error": err,
        }

    issue_ids, missing = _resolve_issue_ids_in_repo(ctx, issue_numbers)
    if missing:
        missing_set = set(missing)
        return {
            "ok": False,
            "sprint_id": sprint_id,
            "sprint_name": actual_sprint_name or sprint_name,
            "outcome": "fail",
            "success_count": 0,
            "failed_count": len(missing),
            "succeeded": [],
            "failed": missing,
            "unaccounted": [n for n in issue_numbers if n not in missing_set],
            "partial_success_warning": None,
            "error": ("Some issue numbers were not found in this repository: " + ", ".join(f"#{n}" for n in missing)),
        }

    data = ctx.execute(
        _ADD_ISSUES_TO_SPRINTS_MUTATION,
        {
            "input": {
                "issueIds": list(issue_ids.values()),
                "sprintIds": [sprint_id],
            }
        },
        context="addIssuesToSprints",
    )
    payload = as_dict(data_get(data, "addIssuesToSprints"))
    returned_links = payload.get("sprintIssues") or []
    succeeded_numbers = _succeeded_numbers_from_add_sprint_links(
        returned_links,
        sprint_id=sprint_id,
        owner_repo=ctx.owner_repo,
    )

    succeeded = [n for n in issue_numbers if n in succeeded_numbers]
    failed = [n for n in issue_numbers if n not in succeeded_numbers]
    outcome = _classify_outcome(len(succeeded), len(failed))

    return {
        "ok": outcome == "ok",
        "sprint_id": sprint_id,
        "sprint_name": actual_sprint_name or sprint_name,
        "outcome": outcome,
        "success_count": len(succeeded),
        "failed_count": len(failed),
        "succeeded": succeeded,
        "failed": failed,
        "unaccounted": [],
        "partial_success_warning": None,
        "error": None,
    }


def remove_issues_from_sprint(ctx: RepoContext, sprint_name: str, issue_numbers: list[int]) -> MutationResult:
    """Remove issues; infer failures from post-mutation sprint membership.

    When ``inspected_full`` is False (walker bailed), only inputs in
    ``walked_numbers`` are classified; others appear in ``response_anomaly``.
    """
    if not issue_numbers:
        raise ZhApiError("issue_numbers must be non-empty")
    for n in issue_numbers:
        if not _is_positive_int(n):
            raise ZhApiError(f"every issue number must be a positive int (got {n!r})")

    issue_numbers = list(dict.fromkeys(issue_numbers))

    sprint_id, actual_sprint_name, err = _find_sprint_id(ctx, sprint_name)
    if err or not sprint_id:
        return {
            "ok": False,
            "sprint_id": None,
            "sprint_name": sprint_name,
            "outcome": "fail",
            "success_count": 0,
            "failed_count": 0,
            "succeeded": [],
            "failed": [],
            "unaccounted": list(issue_numbers),
            "inspected_full": False,
            "pagination_warning": None,
            "response_anomaly": None,
            "partial_success_warning": None,
            "error": err,
        }

    issue_ids, missing = _resolve_issue_ids_in_repo(ctx, issue_numbers)
    if missing:
        missing_set = set(missing)
        return {
            "ok": False,
            "sprint_id": sprint_id,
            "sprint_name": actual_sprint_name or sprint_name,
            "outcome": "fail",
            "success_count": 0,
            "failed_count": len(missing),
            "succeeded": [],
            "failed": missing,
            "unaccounted": [n for n in issue_numbers if n not in missing_set],
            "inspected_full": False,
            "pagination_warning": None,
            "response_anomaly": None,
            "partial_success_warning": None,
            "error": ("Some issue numbers were not found in this repository: " + ", ".join(f"#{n}" for n in missing)),
        }

    data = ctx.execute(
        _REMOVE_ISSUES_FROM_SPRINTS_MUTATION,
        {
            "input": {
                "issueIds": list(issue_ids.values()),
                "sprintIds": [sprint_id],
            }
        },
        context="removeIssuesFromSprints",
    )
    payload = as_dict(data_get(data, "removeIssuesFromSprints"))
    sprints_after = payload.get("sprints") or []

    target_sprint = next(
        (s for s in sprints_after if (s or {}).get("id") == sprint_id),
        None,
    )

    try:
        still_attached_numbers, walked_numbers, inspected_full, pagination_warning, response_anomaly = _resolve_removal_post_state(
            ctx,
            sprint_id=sprint_id,
            target_sprint=target_sprint,
            sprints_after=sprints_after,
        )
    except ZhApiError as walk_err:
        if target_sprint is None:
            base_anomaly = _missing_target_sprint_anomaly(sprint_id, sprints_after)
            return _sprint_removal_walk_error_result(
                sprint_id=sprint_id,
                actual_sprint_name=actual_sprint_name,
                sprint_name=sprint_name,
                issue_numbers=issue_numbers,
                response_anomaly=(base_anomaly + f" Recovery walk also failed: {walk_err}"),
                error=f"Sprint post-state could not be determined: {walk_err}",
            )
        return _sprint_removal_walk_error_result(
            sprint_id=sprint_id,
            actual_sprint_name=actual_sprint_name,
            sprint_name=sprint_name,
            issue_numbers=issue_numbers,
            response_anomaly=(f"Mutation response was full; follow-up walk to confirm post-state failed: {walk_err}"),
            error=f"Sprint post-state could not be confirmed: {walk_err}",
        )

    succeeded, failed, outcome, unaccounted, response_anomaly = _compute_sprint_removal_outcome(
        inspected_full=inspected_full,
        issue_numbers=issue_numbers,
        still_attached_numbers=still_attached_numbers,
        walked_numbers=walked_numbers,
        actual_sprint_name=actual_sprint_name,
        sprint_name=sprint_name,
        pagination_warning=pagination_warning,
        response_anomaly=response_anomaly,
    )

    return {
        "ok": outcome == "ok",
        "sprint_id": sprint_id,
        "sprint_name": actual_sprint_name or sprint_name,
        "outcome": outcome,
        "success_count": len(succeeded),
        "failed_count": len(failed),
        "succeeded": succeeded,
        "failed": failed,
        "unaccounted": unaccounted,
        "inspected_full": inspected_full,
        "pagination_warning": pagination_warning,
        "response_anomaly": response_anomaly,
        "partial_success_warning": None,
        "error": None,
    }
