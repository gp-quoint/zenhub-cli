"""TypedDict schemas for ZenHub API return values."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

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
    issueType: dict[str, Any]
    assignees: dict[str, Any]
    pipelineIssues: dict[str, Any]
    estimate: dict[str, Any]


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


class MutationResult(TypedDict, total=False):
    ok: bool
    parent_number: int
    outcome: Outcome
    success_count: int
    failed_count: int
    succeeded: list[int]
    failed: list[dict[str, Any]]
    unaccounted: list[int]
    failed_unknown_count: int
    github_errors: dict[str, Any] | None
    partial_success_warning: str | None
    error: str
    message: str


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
    issues: dict[str, Any]


class SprintRow(TypedDict, total=False):
    id: str
    name: str
    active: bool


class SprintIssueRow(TypedDict, total=False):
    number: int
    title: str


class SprintListResult(TypedDict, total=False):
    sprints: list[SprintRow]


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
    blocked: str
    blocked_title: str
    blocking: str
    blocking_title: str


class PlanningListItem(TypedDict, total=False):
    number: int
    title: str
    state: str
    repository: dict[str, Any]


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


class GhIssue(TypedDict, total=False):
    title: str
    body: str
    state: str
    url: str
    comments: list[dict[str, Any]]


class GhComment(TypedDict, total=False):
    id: int
    user: str
    created: str
    body: str
