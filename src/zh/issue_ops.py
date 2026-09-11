"""Issue lifecycle GraphQL mutations and helpers."""

from __future__ import annotations

import re

from zh.api import RepoContext, ZhApiError
from zh.gh_ops import github_issue_url, zenhub_issue_url
from zh.graphql_ops import add_sub_issues, get_issue_by_info
from zh.json_helpers import as_dict, as_list, data_get, dict_nodes, json_int
from zh.operations import op
from zh.schemas import (
    AssignResult,
    CreateIssueResult,
    MoveResult,
    ReorderResult,
    UpdateIssueResult,
)
from zh.types import JsonDict, reorder_position
from zh.workspace_ops import find_pipeline_id, resolve_issue_type_id, resolve_priority_id

_POSITIVE_INT = re.compile(r"^[0-9]+$")
_ESTIMATE = re.compile(r"^[0-9]+(\.[0-9]+)?$")

_MOVE_MUTATION = op("issues", "MoveIssue")
_SET_ESTIMATE_MUTATION = op("issues", "SetEstimate")
_SET_PRIORITY_MUTATION = op("issues", "SetPriority")
_CHANGE_TYPE_MUTATION = op("issues", "ChangeIssueTypeOfIssues")
_ISSUE_PIPELINE_QUERY = op("issues", "IssuePipeline")
_ISSUE_ASSIGNEES_QUERY = op("issues", "IssueAssignees")
_WORKSPACE_ASSIGNEES_QUERY = op("issues", "WorkspaceAssignees")
_ADD_ASSIGNEES = op("issues", "AddAssigneesToIssues")
_REMOVE_ASSIGNEES = op("issues", "RemoveAssigneesFromIssues")
_UPDATE_ISSUE = op("issues", "UpdateIssue")
_CREATE_ISSUE = op("issues", "CreateIssue")


def parse_issue_number(raw: str) -> int:
    stripped = raw.lstrip("#")
    if not _POSITIVE_INT.match(stripped):
        msg = f"Invalid issue number: {raw!r}"
        raise ZhApiError(msg)
    return int(stripped)


def _scoped_pipeline_node(node: JsonDict) -> JsonDict:
    """Workspace-scoped pipelineIssue payload (pipeline + optional priority)."""
    return as_dict(node.get("pipelineIssue"))


def _pipeline_name_from_scoped(node: JsonDict) -> str | None:
    name = as_dict(_scoped_pipeline_node(node).get("pipeline")).get("name")
    return str(name) if name else None


def _fetch_issue_pipeline_node(ctx: RepoContext, issue_number: int) -> JsonDict:
    return as_dict(
        ctx.execute_path(
            _ISSUE_PIPELINE_QUERY,
            {
                "repoId": ctx.repo_id,
                "issueNumber": issue_number,
                "workspaceId": ctx.workspace_id,
            },
            "issueByInfo",
            context="issue pipeline lookup",
        ),
    )


def _pipeline_name_before_move(ctx: RepoContext, issue_number: int) -> str:
    """Best-effort current pipeline name for move reporting (never blocks the move)."""
    try:
        name = _pipeline_name_from_scoped(_fetch_issue_pipeline_node(ctx, issue_number))
        return name or "(none)"
    except ZhApiError:
        return "Unknown"


def _dependency_issue_rows(conn: object) -> list[JsonDict]:
    """Normalize GraphQL IssueConnection nodes into agent-stable dependency rows."""
    rows: list[JsonDict] = []
    for node in dict_nodes(as_dict(conn).get("nodes")):
        number = json_int(node.get("number"))
        if number is None:
            continue
        row: JsonDict = {"number": number, "title": str(node.get("title") or "")}
        state = node.get("state")
        if state:
            row["state"] = str(state)
        rows.append(row)
    return rows


def issue_zenhub_summary(ctx: RepoContext, issue_number: int) -> JsonDict:
    """Workspace-scoped board fields for ``zh issue`` (pipeline, estimate, priority, deps, URL)."""
    empty_deps: JsonDict = {"blocked_by": [], "blocking": []}
    try:
        node = _fetch_issue_pipeline_node(ctx, issue_number)
    except ZhApiError:
        return {
            "pipeline": None,
            "estimate": None,
            "priority": None,
            "zenhub_url": zenhub_issue_url(ctx.workspace_id, ctx.owner_repo, issue_number),
            "workspace_id": ctx.workspace_id,
            **empty_deps,
        }
    scoped = _scoped_pipeline_node(node)
    est = as_dict(node.get("estimate")).get("value")
    priority = as_dict(scoped.get("priority")).get("name")
    zh_url = node.get("zenhubUrl") or zenhub_issue_url(ctx.workspace_id, ctx.owner_repo, issue_number)
    # GraphQL: blockingIssues = issues that block this one; blockedIssues = issues this one blocks.
    return {
        "pipeline": _pipeline_name_from_scoped(node),
        "estimate": float(est) if isinstance(est, (int, float)) and not isinstance(est, bool) else None,
        "priority": str(priority) if priority else None,
        "zenhub_url": str(zh_url) if zh_url else None,
        "workspace_id": ctx.workspace_id,
        "blocked_by": _dependency_issue_rows(node.get("blockingIssues")),
        "blocking": _dependency_issue_rows(node.get("blockedIssues")),
    }


def move_issue(ctx: RepoContext, issue_number: int, pipeline_name: str) -> MoveResult:
    pipeline_id = find_pipeline_id(ctx, pipeline_name)
    issue = get_issue_by_info(ctx, issue_number)
    if issue is None:
        raise ZhApiError(f"Issue #{issue_number} not found in ZenHub")
    issue_id = issue.get("id")
    if not isinstance(issue_id, str):
        raise ZhApiError(f"Issue #{issue_number} has no id")
    from_pipeline = _pipeline_name_before_move(ctx, issue_number)
    data = ctx.execute(
        _MOVE_MUTATION,
        {
            "input": {"issueId": issue_id, "pipelineId": pipeline_id, "position": 0},
            "workspaceId": ctx.workspace_id,
        },
        context="moveIssue",
    )
    issue_node = as_dict(data_get(data, "moveIssue", "issue"))
    new_name = _pipeline_name_from_scoped(issue_node)
    if not new_name:
        raise ZhApiError("Failed to move issue")
    return {
        "number": str(issue_number),
        "title": str(issue.get("title") or ""),
        "from_pipeline": from_pipeline,
        "to_pipeline": str(new_name),
    }


def _validate_create_options(
    ctx: RepoContext,
    *,
    parent_number: int | None,
    estimate: str | None,
    priority_name: str | None,
) -> None:
    if parent_number is not None and get_issue_by_info(ctx, parent_number) is None:
        raise ZhApiError(f"Parent issue #{parent_number} not found")
    if estimate and not _ESTIMATE.match(estimate):
        raise ZhApiError(f"Invalid estimate: {estimate!r}")
    if priority_name:
        resolve_priority_id(ctx, priority_name)


def _build_create_input(
    ctx: RepoContext,
    *,
    title: str,
    body: str,
    issue_type: str | None,
    labels: list[str] | None,
    assignee: str | None,
    parent_number: int | None,
    estimate: str | None,
    priority_name: str | None,
) -> JsonDict:
    if not title.strip():
        raise ZhApiError("title must be non-empty")
    _validate_create_options(ctx, parent_number=parent_number, estimate=estimate, priority_name=priority_name)
    inp: JsonDict = {"repositoryId": ctx.repo_id, "title": title}
    if body:
        inp["body"] = body
    if labels:
        inp["labels"] = labels
    if assignee:
        inp["assignees"] = [assignee.lstrip("@")]
    if issue_type:
        inp["issueTypeId"] = resolve_issue_type_id(ctx, issue_type)
    return inp


def _create_issue_record(ctx: RepoContext, inp: JsonDict) -> JsonDict:
    # Do not select issueType: ZenHub exposes it as a union; nested selections fail.
    data = ctx.execute(_CREATE_ISSUE, {"input": inp}, context="createIssue")
    issue = as_dict(data_get(data, "createIssue", "issue"))
    if not issue or not isinstance(issue.get("number"), int):
        raise ZhApiError("createIssue returned no issue number")
    return issue


def _apply_create_followups(
    ctx: RepoContext,
    issue: JsonDict,
    *,
    title: str,
    issue_type: str | None,
    pipeline: str | None,
    estimate: str | None,
    priority_name: str | None,
    parent_number: int | None,
) -> CreateIssueResult:
    number = issue["number"]
    if not isinstance(number, int) or isinstance(number, bool):
        raise ZhApiError("createIssue returned no issue number")
    issue_id = issue.get("id")
    parent_wired: int | None = None
    if parent_number is not None and isinstance(issue_id, str):
        add_result = add_sub_issues(ctx, parent_number, [number])
        if add_result.get("outcome") == "ok":
            parent_wired = parent_number

    pipeline_set = pipeline
    if pipeline:
        move_issue(ctx, number, pipeline)

    estimate_applied = set_estimate(ctx, number, estimate) if estimate else None
    priority_set = set_priority(ctx, number, priority_name) if priority_name else None

    gh_url_raw = issue.get("htmlUrl") or github_issue_url(ctx.owner_repo, number)
    gh_url = str(gh_url_raw) if gh_url_raw else None
    zh_url = zenhub_issue_url(ctx.workspace_id, ctx.owner_repo, number)

    return {
        "number": number,
        "url": gh_url,
        "github_url": gh_url,
        "zenhub_url": zh_url,
        "title": title,
        "type": issue_type,
        "pipeline": pipeline_set,
        "estimate": estimate_applied,
        "estimate_requested": float(estimate) if estimate else None,
        "parent": parent_wired,
        "priority": priority_set,
        "priority_requested": priority_name,
    }


def create_issue(
    ctx: RepoContext,
    *,
    title: str,
    body: str = "",
    issue_type: str | None = None,
    labels: list[str] | None = None,
    assignee: str | None = None,
    pipeline: str | None = None,
    estimate: str | None = None,
    parent_number: int | None = None,
    priority_name: str | None = None,
) -> CreateIssueResult:
    inp = _build_create_input(
        ctx,
        title=title,
        body=body,
        issue_type=issue_type,
        labels=labels,
        assignee=assignee,
        parent_number=parent_number,
        estimate=estimate,
        priority_name=priority_name,
    )
    issue = _create_issue_record(ctx, inp)
    return _apply_create_followups(
        ctx,
        issue,
        title=title,
        issue_type=issue_type,
        pipeline=pipeline,
        estimate=estimate,
        priority_name=priority_name,
        parent_number=parent_number,
    )


def set_estimate(ctx: RepoContext, issue_number: int, points: str) -> float | None:
    if points.lower() == "clear":
        value: float | None = None
    elif _ESTIMATE.match(points):
        value = float(points)
    else:
        raise ZhApiError(f"Invalid estimate: {points!r}")
    issue = get_issue_by_info(ctx, issue_number)
    if issue is None:
        raise ZhApiError(f"Issue #{issue_number} not found")
    issue_id = issue.get("id")
    if not isinstance(issue_id, str):
        raise ZhApiError(f"Issue #{issue_number} has no id")
    data = ctx.execute(
        _SET_ESTIMATE_MUTATION,
        {"input": {"issueId": issue_id, "value": value}},
        context="setEstimate",
    )
    applied = as_dict(as_dict(data_get(data, "setEstimate", "issue")).get("estimate")).get("value")
    if applied is None:
        return None
    if isinstance(applied, bool):
        return None
    if isinstance(applied, (int, float)):
        return float(applied)
    return None


def set_priority(ctx: RepoContext, issue_number: int, level: str) -> str | None:
    priority_id = None if level.lower() == "clear" else resolve_priority_id(ctx, level)
    issue = get_issue_by_info(ctx, issue_number)
    if issue is None:
        raise ZhApiError(f"Issue #{issue_number} not found")
    issue_id = issue.get("id")
    if not isinstance(issue_id, str):
        raise ZhApiError(f"Issue #{issue_number} has no id")
    data = ctx.execute(
        _SET_PRIORITY_MUTATION,
        {"input": {"issueId": issue_id, "priorityId": priority_id}},
        context="setPriority",
    )
    name = as_dict(as_dict(data_get(data, "setPriority", "pipelineIssue")).get("priority")).get("name")
    return str(name) if name else None


def set_issue_type(ctx: RepoContext, issue_number: int, type_name: str) -> str:
    type_id = resolve_issue_type_id(ctx, type_name)
    issue = get_issue_by_info(ctx, issue_number)
    if issue is None:
        raise ZhApiError(f"Issue #{issue_number} not found")
    issue_id = issue.get("id")
    if not isinstance(issue_id, str):
        raise ZhApiError(f"Issue #{issue_number} has no id")
    data = ctx.execute(
        _CHANGE_TYPE_MUTATION,
        {"input": {"issueIds": [issue_id], "issueTypeId": type_id}},
        context="changeIssueTypeOfIssues",
    )
    issues = as_list(as_dict(data_get(data, "changeIssueTypeOfIssues")).get("issues"))
    if not issues:
        raise ZhApiError("Failed to change issue type")
    applied = as_dict(as_dict(issues[0]).get("issueType")).get("name")
    return str(applied or type_name)


def _issue_pipeline_info(ctx: RepoContext, issue_number: int) -> tuple[str, str, str, int]:
    issue = get_issue_by_info(ctx, issue_number)
    if issue is None:
        raise ZhApiError(f"Issue #{issue_number} not found in ZenHub")
    issue_id = issue.get("id")
    if not isinstance(issue_id, str):
        raise ZhApiError(f"Issue #{issue_number} has no id")
    node = _fetch_issue_pipeline_node(ctx, issue_number)
    pipeline_node = as_dict(_scoped_pipeline_node(node).get("pipeline"))
    pipeline_id = pipeline_node.get("id")
    total = as_dict(pipeline_node.get("issues")).get("totalCount") or 0
    if not isinstance(pipeline_id, str):
        raise ZhApiError(f"Issue #{issue_number} is not in any pipeline for this workspace")
    return issue_id, str(node.get("title") or issue.get("title") or ""), pipeline_id, json_int(total)


def _parse_reorder_position(raw: str, total_count: int) -> int:
    try:
        return reorder_position(raw, total_count=total_count)
    except ValueError as exc:
        raise ZhApiError(str(exc)) from exc


def reorder_issue(ctx: RepoContext, issue_number: int, position: str) -> ReorderResult:
    issue_id, title, pipeline_id, total = _issue_pipeline_info(ctx, issue_number)
    pos_int = _parse_reorder_position(position, total)
    ctx.execute(
        _MOVE_MUTATION,
        {
            "input": {"issueId": issue_id, "pipelineId": pipeline_id, "position": pos_int},
            "workspaceId": ctx.workspace_id,
        },
        context="reorderIssue",
    )
    return {"number": issue_number, "title": title, "position": pos_int}


def _fetch_issue_assignees(ctx: RepoContext, issue_number: int) -> JsonDict:
    node = ctx.execute_path(
        _ISSUE_ASSIGNEES_QUERY,
        {"repoId": ctx.repo_id, "issueNumber": issue_number},
        "issueByInfo",
        context="issue assignees",
    )
    if not node:
        raise ZhApiError(f"Issue #{issue_number} not found")
    return as_dict(node)


def _workspace_assignees(ctx: RepoContext) -> list[dict[str, str]]:
    workspace = ctx.execute_path(
        _WORKSPACE_ASSIGNEES_QUERY,
        {"workspaceId": ctx.workspace_id},
        "workspace",
        context="workspace assignees",
    )
    nodes = dict_nodes(as_dict(as_dict(workspace).get("assignees")).get("nodes"))
    return [{"id": str(n.get("id")), "login": str(n.get("login"))} for n in nodes if n.get("id") and n.get("login")]


def assign_issue(ctx: RepoContext, issue_number: int, usernames: list[str]) -> AssignResult:
    if not usernames:
        raise ZhApiError("Usage: zh assign <issue> <username> [username ...]")
    wanted = list(dict.fromkeys(u.lstrip("@") for u in usernames))
    issue = _fetch_issue_assignees(ctx, issue_number)
    issue_id = issue.get("id")
    if not isinstance(issue_id, str):
        raise ZhApiError(f"Issue #{issue_number} has no id")
    title = str(issue.get("title") or "")
    current = [str(n.get("login")) for n in dict_nodes(as_dict(issue.get("assignees")).get("nodes")) if n.get("login")]
    ws_users = _workspace_assignees(ctx)
    ws_logins = {u["login"] for u in ws_users}
    missing = [u for u in wanted if u not in ws_logins]
    if missing:
        raise ZhApiError(f"User(s) not found in workspace: {', '.join(missing)}. Use 'zh users' to list available users.")
    ids_to_add = [u["id"] for u in ws_users if u["login"] in wanted and u["login"] not in current]
    if not ids_to_add:
        return {"number": issue_number, "title": title, "assignees": current, "already_assigned": wanted}
    data = ctx.execute(
        _ADD_ASSIGNEES,
        {"input": {"issueIds": [issue_id], "assigneeIds": ids_to_add}},
        context="addAssigneesToIssues",
    )
    success_count = as_dict(data_get(data, "addAssigneesToIssues")).get("successCount") or 0
    if success_count == 0:
        gh_errors = as_dict(data_get(data, "addAssigneesToIssues")).get("githubErrors")
        raise ZhApiError(f"Failed to assign {', '.join(wanted)}: {gh_errors or 'Unknown error'}")
    updated = _fetch_issue_assignees(ctx, issue_number)
    new_assignees = [str(n.get("login")) for n in dict_nodes(as_dict(updated.get("assignees")).get("nodes")) if n.get("login")]
    return {"number": issue_number, "title": title, "assignees": new_assignees, "added": wanted}


def unassign_issue(
    ctx: RepoContext,
    issue_number: int,
    usernames: list[str],
    *,
    clear_all: bool = False,
) -> AssignResult:
    if clear_all and usernames:
        raise ZhApiError("Pass specific username(s) OR --all, not both.")
    if not clear_all and not usernames:
        raise ZhApiError(
            "Refusing to remove all assignees by default (this is a destructive, shared-state change).\n"
            f"Name the user(s) to remove, or pass --all to clear everyone:\n"
            f"  zh unassign {issue_number} <username> [username ...]\n"
            f"  zh unassign {issue_number} --all",
        )
    issue = _fetch_issue_assignees(ctx, issue_number)
    issue_id = issue.get("id")
    if not isinstance(issue_id, str):
        raise ZhApiError(f"Issue #{issue_number} has no id")
    title = str(issue.get("title") or "")
    nodes = dict_nodes(as_dict(issue.get("assignees")).get("nodes"))
    if clear_all:
        ids_to_remove = [str(n.get("id")) for n in nodes if n.get("id")]
        if not ids_to_remove:
            raise ZhApiError(f"Issue #{issue_number} has no assignees")
        removed_label = "all assignees"
    else:
        wanted = list(dict.fromkeys(u.lstrip("@") for u in usernames))
        current_logins = {str(n.get("login")) for n in nodes if n.get("login")}
        not_assigned = [u for u in wanted if u not in current_logins]
        if not_assigned:
            assigned = ", ".join(sorted(current_logins)) or "none"
            raise ZhApiError(f"Not assigned to issue #{issue_number}: {', '.join(not_assigned)}\nCurrent assignees: {assigned}")
        ids_to_remove = [str(n.get("id")) for n in nodes if str(n.get("login")) in wanted]
        removed_label = ", ".join(wanted)
    data = ctx.execute(
        _REMOVE_ASSIGNEES,
        {"input": {"issueIds": [issue_id], "assigneeIds": ids_to_remove}},
        context="removeAssigneesFromIssues",
    )
    success_count = as_dict(data_get(data, "removeAssigneesFromIssues")).get("successCount") or 0
    if success_count == 0:
        gh_errors = as_dict(data_get(data, "removeAssigneesFromIssues")).get("githubErrors")
        raise ZhApiError(f"Failed to remove assignee(s): {gh_errors or 'Unknown error'}")
    updated = _fetch_issue_assignees(ctx, issue_number)
    remaining = [str(n.get("login")) for n in dict_nodes(as_dict(updated.get("assignees")).get("nodes")) if n.get("login")]
    return {"number": issue_number, "title": title, "assignees": remaining, "removed": removed_label}


def update_issue(
    ctx: RepoContext,
    issue_number: int,
    *,
    title: str | None = None,
    body: str | None = None,
) -> UpdateIssueResult:
    if title is None and body is None:
        raise ZhApiError("Nothing to update: provide -t (title) and/or -d (description).")
    issue = get_issue_by_info(ctx, issue_number)
    if issue is None:
        raise ZhApiError(f"Issue #{issue_number} not found")
    issue_id = issue.get("id")
    if not isinstance(issue_id, str):
        raise ZhApiError(f"Issue #{issue_number} has no id")
    inp: JsonDict = {"issueId": issue_id}
    if title is not None:
        inp["title"] = title
    if body is not None:
        inp["body"] = body
    data = ctx.execute(_UPDATE_ISSUE, {"input": inp}, context="updateIssue")
    updated = as_dict(data_get(data, "updateIssue", "issue"))
    resulting_title = updated.get("title")
    if not resulting_title:
        raise ZhApiError(f"Failed to update #{issue_number}")
    return {"number": issue_number, "title": str(resulting_title)}
