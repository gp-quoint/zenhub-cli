"""Workspace-level GraphQL reads: pipelines, types, priorities, labels."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, cast

from zh.api import RepoContext, ZhApiError, get_gh_repo_id
from zh.json_helpers import as_dict, data_get, dict_nodes
from zh.operations import op
from zh.schemas import (
    BoardOverview,
    IssueTypeRow,
    LabelRow,
    PipelineIssueRow,
    PipelineIssuesResult,
    PipelineNode,
    PriorityRow,
)

_PIPELINES_QUERY = op("workspace", "PipelinesOpen")

_PIPELINES_ALL_QUERY = op("workspace", "PipelinesAll")

_ISSUE_TYPES_QUERY = op("workspace", "AssignableIssueTypes")

_PRIORITIES_QUERY = op("workspace", "Priorities")

_LABELS_QUERY = op("workspace", "Labels")

_PIPELINE_ISSUES_QUERY = op("workspace", "SearchIssuesByPipeline")


@lru_cache(maxsize=16)
def _cached_pipeline_nodes(workspace_id: str, token: str) -> tuple[tuple[str | None, str | None], ...]:
    ctx = RepoContext("", "", workspace_id, token)
    ws = ctx.execute_path(_PIPELINES_QUERY, {"workspaceId": workspace_id}, "workspace", context="workspace")
    if not ws:
        raise ZhApiError("Workspace not found")
    nodes = dict_nodes(as_dict(as_dict(ws).get("pipelinesConnection")).get("nodes"))
    return tuple((node.get("id"), node.get("name")) for node in nodes)


def list_pipelines(ctx: RepoContext) -> list[PipelineNode]:
    cached = _cached_pipeline_nodes(ctx.workspace_id, ctx.token)
    return cast(list[PipelineNode], [{"id": pid, "name": name} for pid, name in cached])


def _pipeline_display_names(pipelines: list[PipelineNode]) -> str:
    return ", ".join(n.get("name") or "?" for n in pipelines) or "(none)"


def resolve_pipeline(ctx: RepoContext, name: str) -> PipelineNode:
    """Resolve a pipeline by exact, unique-prefix, or unique-substring match (case-insensitive)."""
    want = name.strip().casefold()
    if not want:
        raise ZhApiError(f"Pipeline {name!r} not found. Available: {_pipeline_display_names(list_pipelines(ctx))}")
    pipelines = list_pipelines(ctx)

    def _folded(node: PipelineNode) -> str:
        return (node.get("name") or "").strip().casefold()

    exact = [node for node in pipelines if _folded(node) == want]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ZhApiError(
            f"Pipeline {name!r} is ambiguous; matches: {_pipeline_display_names(exact)}",
        )

    prefixes = [node for node in pipelines if _folded(node).startswith(want)]
    if len(prefixes) == 1:
        return prefixes[0]
    if len(prefixes) > 1:
        raise ZhApiError(
            f"Pipeline {name!r} is ambiguous; matches: {_pipeline_display_names(prefixes)}. "
            f"Available: {_pipeline_display_names(pipelines)}",
        )

    substrings = [node for node in pipelines if want in _folded(node)]
    if len(substrings) == 1:
        return substrings[0]
    if len(substrings) > 1:
        raise ZhApiError(
            f"Pipeline {name!r} is ambiguous; matches: {_pipeline_display_names(substrings)}. "
            f"Available: {_pipeline_display_names(pipelines)}",
        )

    raise ZhApiError(
        f"Pipeline {name!r} not found. Available: {_pipeline_display_names(pipelines)}",
    )


def find_pipeline_id(ctx: RepoContext, name: str) -> str:
    node = resolve_pipeline(ctx, name)
    pipeline_id = node.get("id")
    if not isinstance(pipeline_id, str) or not pipeline_id:
        raise ZhApiError(f"Pipeline {name!r} has no id")
    return pipeline_id


def board_overview(ctx: RepoContext, *, include_closed: bool = False) -> BoardOverview:
    query = _PIPELINES_ALL_QUERY if include_closed else _PIPELINES_QUERY
    ws = ctx.execute_path(query, {"workspaceId": ctx.workspace_id}, "workspace", context="board")
    if not ws:
        raise ZhApiError("Workspace not found")
    ws_dict = as_dict(ws)
    pipelines = dict_nodes(as_dict(ws_dict.get("pipelinesConnection")).get("nodes"))
    counts = {str(p.get("name") or "?"): int(as_dict(p.get("issues")).get("totalCount") or 0) for p in pipelines}
    total = sum(counts.values())
    return {
        "workspace": ws_dict.get("name"),
        "pipelines": counts,
        "total": total,
        "include_closed": include_closed,
    }


def fetch_issue_types(ctx: RepoContext) -> list[IssueTypeRow]:
    gh_id = get_gh_repo_id(ctx.owner_repo)
    data = ctx.execute(
        _ISSUE_TYPES_QUERY,
        {"ghIds": [gh_id], "workspaceId": ctx.workspace_id},
        context="assignableIssueTypes",
    )
    repos = dict_nodes(data_get(data, "repositoriesByGhId"))
    if not repos:
        return []
    first = as_dict(repos[0])
    nodes = dict_nodes(as_dict(first.get("assignableIssueTypes")).get("nodes"))
    return cast(
        list[IssueTypeRow],
        [
            {
                "typename": n.get("__typename"),
                "id": n.get("id"),
                "name": n.get("name"),
                "level": n.get("level"),
                "disposition": n.get("disposition"),
                "isEnabled": n.get("isEnabled"),
            }
            for n in nodes
            if n.get("isEnabled") is not False
        ],
    )


def resolve_issue_type_id(ctx: RepoContext, type_name: str) -> str:
    want = type_name.casefold()
    for row in fetch_issue_types(ctx):
        if (row.get("name") or "").casefold() == want:
            type_id = row.get("id")
            if isinstance(type_id, str) and type_id:
                return type_id
    names = ", ".join(r.get("name") or "?" for r in fetch_issue_types(ctx))
    raise ZhApiError(
        f"Issue type {type_name!r} not found. Available: {names or '(none)'}",
    )


def fetch_priorities(ctx: RepoContext) -> list[PriorityRow]:
    ws = as_dict(ctx.execute_path(_PRIORITIES_QUERY, {"workspaceId": ctx.workspace_id}, "workspace", context="priorities"))
    return cast(list[PriorityRow], dict_nodes(as_dict(ws.get("prioritiesConnection")).get("nodes")))


def resolve_priority_id(ctx: RepoContext, priority_name: str) -> str:
    want = priority_name.casefold()
    for row in fetch_priorities(ctx):
        if (row.get("name") or "").casefold() == want:
            pid = row.get("id")
            if isinstance(pid, str) and pid:
                return pid
    names = ", ".join(r.get("name") or "?" for r in fetch_priorities(ctx)) or "(none)"
    raise ZhApiError(f"No priority named {priority_name!r}. Available: {names}")


def fetch_labels(ctx: RepoContext) -> list[LabelRow]:
    gh_id = get_gh_repo_id(ctx.owner_repo)
    data = ctx.execute(_LABELS_QUERY, {"ghIds": [gh_id]}, context="labels")
    repos = dict_nodes(data_get(data, "repositoriesByGhId"))
    if not repos:
        return []
    first = as_dict(repos[0])
    return cast(list[LabelRow], dict_nodes(as_dict(first.get("labels")).get("nodes")))


def pipeline_issues(
    ctx: RepoContext,
    pipeline_name: str,
    *,
    assignee: str | None = None,
    pipeline_id: str | None = None,
) -> PipelineIssuesResult:
    resolved_pipeline_id = pipeline_id or find_pipeline_id(ctx, pipeline_name)
    filters: dict[str, Any] = {}
    if assignee:
        filters["assignees"] = {"in": [assignee.lstrip("@")]}
    data = ctx.execute(
        _PIPELINE_ISSUES_QUERY,
        {
            "pipelineId": resolved_pipeline_id,
            "workspaceId": ctx.workspace_id,
            "filters": filters,
        },
        context="searchIssuesByPipeline",
    )
    nodes = dict_nodes(as_dict(data_get(data, "searchIssuesByPipeline")).get("nodes"))
    issues: list[PipelineIssueRow] = []
    for node in nodes:
        repo = as_dict(node.get("repository"))
        owner = repo.get("ownerName") or ""
        name = repo.get("name") or ""
        assignees = [str(a.get("login")) for a in dict_nodes(as_dict(node.get("assignees")).get("nodes")) if a.get("login")]
        est = as_dict(node.get("estimate")).get("value")
        issues.append(
            cast(
                PipelineIssueRow,
                {
                    "number": node.get("number"),
                    "title": node.get("title"),
                    "repo": f"{owner}/{name}" if owner and name else ctx.owner_repo,
                    "estimate": est,
                    "assignee": assignees[0] if assignees else None,
                    "url": node.get("zenhubUrl"),
                },
            ),
        )
    return {"pipeline": pipeline_name, "issues": issues}
