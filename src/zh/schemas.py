"""TypedDict schemas for ZenHub API return values."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from zh.types import JsonDict

Outcome = Literal["ok", "partial", "fail", "noop"]
DuplicateRecommendation = Literal["create", "warn", "block"]


class WorkspaceRow(TypedDict):
    id: str
    name: str


class IssueInfo(TypedDict, total=False):
    id: str
    number: int
    title: str
    state: str
    body: str
    issueType: JsonDict
    assignees: JsonDict
    pipelineIssues: JsonDict
    estimate: JsonDict
    htmlUrl: str
    parentIssue: JsonDict


class SubIssueChild(TypedDict, total=False):
    id: str
    number: int
    title: str
    state: str
    pipeline: str | None
    pipeline_workspace_scoped: bool
    assignees: list[str]
    repository: dict[str, str]


class SubIssueListResult(TypedDict, total=False):
    ok: bool
    parent_number: int
    parent_title: str
    parent_state: str | None
    total_count: int
    fetched_count: int
    children: list[SubIssueChild]
    pagination_warning: str | None
    error: str


class FailedIssueRef(TypedDict, total=False):
    number: int | None
    owner: str
    name: str


class CrossRepoChild(TypedDict):
    number: int
    owner: str
    name: str


class WrongParentChild(TypedDict):
    number: int
    actual_parent: int | None


class MutationResult(TypedDict, total=False):
    ok: bool
    parent_number: int
    child_number: int
    position: str
    outcome: Outcome
    success_count: int
    failed_count: int
    succeeded: list[int]
    failed: list[FailedIssueRef | int]
    unaccounted: list[int]
    failed_unknown_count: int
    github_errors: JsonDict | None
    partial_success_warning: str | None
    error: str | None
    message: str | None
    sprint_id: str
    sprint_name: str
    inspected_full: bool
    pagination_warning: str | None
    response_anomaly: str | None


class DuplicateMatch(TypedDict, total=False):
    number: int
    title: str
    similarity: float
    meets_threshold: bool
    match_kind: str
    state: str
    url: str


class DuplicateCheckResult(TypedDict, total=False):
    ok: bool
    matches: list[DuplicateMatch]
    any_above_hard: bool
    any_above_soft: bool
    downgraded_structural: bool
    recommendation: DuplicateRecommendation
    hard_threshold: float
    soft_threshold: float


class ReindexResult(TypedDict, total=False):
    ok: bool
    repo: str
    mode: str
    added: int
    updated: int
    removed: int
    indexed_at: str
    total_entries: int
    full: bool


class BoardOverview(TypedDict):
    workspace: str | None
    pipelines: dict[str, int]
    total: int
    include_closed: bool


class PipelineIssueRow(TypedDict, total=False):
    number: int
    title: str
    repo: str
    estimate: float | None
    assignee: str | None
    url: str
    pipeline: str


class PipelineIssuesResult(TypedDict):
    pipeline: str
    issues: list[PipelineIssueRow]


class IssueTypeRow(TypedDict, total=False):
    typename: str
    id: str
    name: str
    level: int
    disposition: str
    isEnabled: bool


class PriorityRow(TypedDict, total=False):
    id: str
    name: str
    color: str


class LabelRow(TypedDict, total=False):
    name: str
    color: str


class PipelineNode(TypedDict, total=False):
    id: str
    name: str
    issues: JsonDict


class SprintRow(TypedDict, total=False):
    id: str
    name: str
    state: str
    start_at: str | None
    end_at: str | None
    completed_points: float
    total_points: float
    closed_issues_count: int
    is_active: bool
    # Legacy alias used by some callers; prefer is_active.
    active: bool


class SprintIssueRow(TypedDict, total=False):
    number: int
    title: str
    state: str
    html_url: str
    estimate: float | None
    assignees: list[str]
    pipeline: str | None
    repository: dict[str, str]


class SprintListResult(TypedDict, total=False):
    ok: bool
    workspace_name: str
    active_sprint_id: str | None
    sprints: list[SprintRow]
    pagination_warning: str | None


class SprintDetailResult(TypedDict, total=False):
    ok: bool
    sprint_id: str | None
    sprint_name: str
    state: str | None
    start_at: str | None
    end_at: str | None
    completed_points: float
    total_points: float
    closed_issues_count: int
    description: str | None
    issue_count: int
    issues: list[SprintIssueRow]
    pagination_warning: str | None
    error: str | None


class CreateIssueResult(TypedDict):
    number: int
    title: str
    url: NotRequired[str | None]  # GitHub HTML URL (alias of github_url)
    github_url: NotRequired[str | None]
    zenhub_url: NotRequired[str | None]
    type: NotRequired[str | None]
    pipeline: NotRequired[str | None]
    estimate: NotRequired[float | None]
    estimate_requested: NotRequired[float | None]
    parent: NotRequired[int | None]
    priority: NotRequired[str | None]
    priority_requested: NotRequired[str | None]


class UpdateIssueResult(TypedDict):
    number: int
    title: str


class AssignResult(TypedDict):
    number: int
    title: str
    assignees: list[str]
    added: NotRequired[list[str]]
    already_assigned: NotRequired[list[str]]
    removed: NotRequired[str]


class MoveResult(TypedDict):
    number: str
    title: str
    from_pipeline: str
    to_pipeline: str


class ReorderResult(TypedDict):
    number: int
    title: str
    position: int


class BlockageResult(TypedDict):
    blocked: int
    blocked_title: str
    blocking: int
    blocking_title: str


class UnblockResult(TypedDict):
    blocked: int
    blocking: int
    removed: bool


class DependencyIssue(TypedDict, total=False):
    number: int
    title: str
    state: str


class IssueZenhubSummary(TypedDict):
    pipeline: str | None
    estimate: float | None
    priority: str | None
    zenhub_url: str | None
    workspace_id: str
    blocked_by: list[DependencyIssue]
    blocking: list[DependencyIssue]


class PlanningListItem(TypedDict, total=False):
    number: int
    title: str
    state: str
    repository: dict[str, str]


class PlanningListResult(TypedDict):
    type: str
    workspace: str | None
    total_count: int
    fetched_count: int
    items: list[PlanningListItem]


class PlanningChildRow(TypedDict, total=False):
    number: int
    title: str
    state: str
    pipeline: str
    assignees: list[str]


class PlanningShowResult(TypedDict, total=False):
    sub_issues: SubIssueListResult
    parent_number: int
    issue_type: str | None
    total_count: int
    fetched_count: int
    children: list[PlanningChildRow]


class GhComment(TypedDict, total=False):
    id: int
    user: str
    created: str
    body: str
    index: int  # 1-based for zh comment edit


class GhIssue(TypedDict, total=False):
    title: str
    body: str
    state: str
    url: str
    comments: list[GhComment]
