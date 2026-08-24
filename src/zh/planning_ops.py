"""Planning-hierarchy helpers (Initiative / Project / Epic / Sub-task)."""

from __future__ import annotations

from typing import cast

from zh.api import RepoContext, ZhApiError
from zh.cli.output import warn
from zh.graphql_ops import get_issue_by_info, list_sub_issues
from zh.json_helpers import as_dict, dict_nodes
from zh.operations import op
from zh.schemas import PlanningChildRow, PlanningListItem, PlanningListResult, PlanningShowResult
from zh.workspace_ops import fetch_issue_types, resolve_issue_type_id

_PLANNING_NOUNS = frozenset({"initiative", "project", "epic", "sub-task", "subtask"})

_LIST_BY_TYPE = op("planning", "ListByIssueType")

_CHILDREN_DETAIL = op("planning", "HierarchyChildrenDetail")


def display_noun(type_name: str) -> str:
    if type_name.lower() == "sub-task":
        return "subtask"
    return type_name.lower()


def canonical_type_name(ctx: RepoContext, type_name: str) -> str:
    rows = fetch_issue_types(ctx)
    lower = type_name.lower()
    for row in rows:
        name = str(row.get("name") or "")
        if name.lower() == lower:
            return name
    available = ", ".join(str(r.get("name") or "") for r in rows if r.get("name")) or "(none)"
    raise ZhApiError(
        f"Issue type {type_name!r} is not assignable in this workspace. Available: {available}. Discover with 'zh types'.",
    )


def list_issues_by_type(ctx: RepoContext, type_name: str) -> PlanningListResult:
    canonical = canonical_type_name(ctx, type_name)
    ws = as_dict(
        ctx.execute_path(
            _LIST_BY_TYPE,
            {"workspaceId": ctx.workspace_id, "typeName": canonical},
            "workspace",
            context="planning list",
        ),
    )
    issues_conn = as_dict(ws.get("issues"))
    nodes = dict_nodes(issues_conn.get("nodes"))
    items = [
        {
            "number": n.get("number"),
            "title": n.get("title"),
            "state": n.get("state"),
            "repository": n.get("repository"),
        }
        for n in nodes
    ]
    return {
        "type": canonical,
        "workspace": ws.get("name"),
        "total_count": int(issues_conn.get("totalCount") or 0),
        "fetched_count": len(nodes),
        "items": cast(list[PlanningListItem], items),
    }


def hierarchy_children_detail(ctx: RepoContext, parent_number: int) -> PlanningShowResult:
    node = ctx.execute_path(
        _CHILDREN_DETAIL,
        {"repoId": ctx.repo_id, "issueNumber": parent_number, "workspaceId": ctx.workspace_id},
        "issueByInfo",
        context="hierarchy children",
    )
    if not node:
        raise ZhApiError(f"Issue #{parent_number} not found")
    node_dict = as_dict(node)
    children_conn = as_dict(node_dict.get("githubChildIssues"))
    children: list[PlanningChildRow] = []
    for child in dict_nodes(children_conn.get("nodes")):
        assignees = [str(a.get("login")) for a in dict_nodes(as_dict(child.get("assignees")).get("nodes")) if a.get("login")]
        pipe = as_dict(as_dict(child.get("pipelineIssue")).get("pipeline")).get("name") or "-"
        children.append(
            cast(
                PlanningChildRow,
                {
                    "number": child.get("number"),
                    "title": child.get("title"),
                    "state": child.get("state"),
                    "pipeline": pipe,
                    "assignees": assignees,
                },
            ),
        )
    return {
        "parent_number": parent_number,
        "issue_type": as_dict(node_dict.get("issueType")).get("name"),
        "total_count": int(children_conn.get("totalCount") or 0),
        "fetched_count": len(children),
        "children": children,
    }


def warn_type_mismatch(ctx: RepoContext, expected_type: str, issue_number: int, verb: str) -> None:
    issue = get_issue_by_info(ctx, issue_number)
    if not issue:
        return
    actual = as_dict(issue.get("issueType")).get("name")
    if not actual or str(actual).lower() == expected_type.lower():
        return
    actual_lower = display_noun(str(actual))
    match (actual_lower, verb):
        case (noun, _) if noun in _PLANNING_NOUNS:
            redirect = f"zh {noun} {verb} {issue_number}"
        case (_, "close" | "reopen"):
            redirect = f"zh {verb} {issue_number}"
        case (_, "update"):
            redirect = ""
        case _:
            redirect = f"zh issue {issue_number}"
    match verb:
        case "show" if redirect:
            trailing = f"The data still rendered, but the matching command is '{redirect}'."
        case _ if redirect:
            trailing = f"The {verb} still applied to #{issue_number}; next time the matching command is '{redirect}'."
        case _:
            trailing = (
                f"The {verb} still applied to #{issue_number}. "
                f"(No matching top-level command exists for {actual}; retype with "
                f"'zh type {issue_number} {expected_type}' first if you want {expected_type} semantics.)"
            )
    warn(f"Issue #{issue_number} is typed {actual}, not {expected_type}. {trailing}")


def ensure_type_for_create(ctx: RepoContext, type_name: str) -> str:
    """Resolve type id and return canonical name."""
    canonical = canonical_type_name(ctx, type_name)
    resolve_issue_type_id(ctx, canonical)
    return canonical


def show_planning_issue(ctx: RepoContext, expected_type: str, issue_number: int) -> PlanningShowResult:
    warn_type_mismatch(ctx, expected_type, issue_number, "show")
    subs = list_sub_issues(ctx, issue_number)
    detail = hierarchy_children_detail(ctx, issue_number)
    return {"sub_issues": subs, **detail}
