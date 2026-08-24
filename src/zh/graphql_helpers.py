"""Shared GraphQL response parsing helpers for sub-issue mutations."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypedDict, cast

from zh.json_helpers import as_dict, dict_nodes, json_int
from zh.schemas import (
    CrossRepoChild,
    FailedIssueRef,
    MutationResult,
    Outcome,
    SprintIssueRow,
    SubIssueChild,
    WrongParentChild,
)
from zh.types import JsonDict


class PageInfo(TypedDict, total=False):
    hasNextPage: bool
    endCursor: str | None


def paginate_pages[T](
    fetch_page: Callable[[str | None], tuple[list[T], PageInfo]],
    *,
    max_pages: int = 200,
    stuck_warning: str = (
        "Pagination cursor not advancing across requests — server likely mis-reporting hasNextPage. Bailing."
    ),
    cap_warning: str | None = None,
) -> tuple[list[T], str | None]:
    """Walk a GraphQL connection via ``fetch_page(after) -> (nodes, pageInfo)``.

    Returns ``(items, warning)``. Stops on no next page, stuck cursor, or ``max_pages``.
    """
    items: list[T] = []
    cursor: str | None = None
    last_cursor: str | None = None
    warning: str | None = None
    cap_msg = cap_warning or f"Pagination iteration cap ({max_pages}) exceeded — bailing"

    for _ in range(max_pages):
        page_items, page_info = fetch_page(cursor)
        items.extend(page_items)
        if not page_info.get("hasNextPage"):
            return items, warning
        end_cursor = page_info.get("endCursor")
        if not end_cursor or end_cursor == last_cursor:
            return items, stuck_warning
        last_cursor = end_cursor
        cursor = end_cursor

    return items, cap_msg


def serialize_failed_issues(failed_issues: list[object]) -> list[FailedIssueRef]:
    out: list[FailedIssueRef] = []
    for fi in failed_issues:
        node = as_dict(fi)
        repo = as_dict(node.get("repository"))
        number = node.get("number")
        out.append(
            {
                "number": number if isinstance(number, int) and not isinstance(number, bool) else None,
                "owner": str(repo.get("ownerName") or ""),
                "name": str(repo.get("name") or ""),
            }
        )
    return out


def _divergence_warning(
    *,
    outcome: str,
    divergence: bool,
    success_count: int,
    inferred_succeeded: list[int],
    child_numbers: list[int],
    failed_count: int,
    unaccounted: list[int],
    failed_unknown_count: int,
    partial_success_warning: str | None,
) -> str | None:
    warning = partial_success_warning
    if divergence:
        if outcome == "partial":
            warning = (
                f"API returned successCount={success_count} but inferred "
                f"succeeded set has {len(inferred_succeeded)} entries "
                "(divergence). Cannot identify which inputs succeeded. "
                "Re-list the parent's children to determine actual state."
            )
        elif outcome == "noop":
            warning = (
                "API returned strict no-op (successCount=0, "
                f"failedIssues=[]) despite {len(child_numbers)} input(s). "
                "The mutation may have silently rejected all inputs, or "
                "the inputs were already in the requested state. Re-list "
                "to confirm."
            )
        elif outcome == "fail":
            warning = (
                f"API reported {failed_count} failure(s) but did not "
                f"report on {len(unaccounted)} input(s) (neither "
                "succeeded nor in failedIssues). Those inputs' state "
                "is undetermined. Re-list to confirm."
            )
    if failed_unknown_count > 0:
        anon_note = (
            f"{failed_unknown_count} failedIssues entries had no usable "
            "issue number; those inputs cannot be identified and are "
            "not present in `failed` or `unaccounted`."
        )
        warning = f"{warning} {anon_note}" if warning else anon_note
    return warning


def finalize_child_mutation_payload(
    *,
    child_numbers: list[int],
    parent_number: int,
    payload: JsonDict,
    classify_outcome: Callable[[int, int], Outcome],
) -> MutationResult:
    success_count = json_int(payload.get("successCount"))
    failed_raw = payload.get("failedIssues")
    failed_issues: list[object] = cast(list[object], failed_raw) if isinstance(failed_raw, list) else []
    failed_count = len(failed_issues)
    github_raw = payload.get("githubErrors")
    github_errors = cast(JsonDict, github_raw) if isinstance(github_raw, dict) and github_raw else None

    failed_serialized = serialize_failed_issues(failed_issues)
    failed_numbers = {n for fi in failed_serialized if (n := fi.get("number")) is not None}
    failed_unknown_count = failed_count - len(failed_numbers)
    inferred_succeeded = [n for n in child_numbers if n not in failed_numbers]
    divergence = success_count != len(inferred_succeeded)
    succeeded = inferred_succeeded if not divergence else []

    outcome = classify_outcome(success_count, failed_count)
    if divergence and outcome == "ok":
        outcome = "partial"

    accounted: set[int] = set(failed_numbers) | set(succeeded)
    unaccounted = [n for n in child_numbers if n not in accounted]
    partial_success_warning = _divergence_warning(
        outcome=outcome,
        divergence=divergence,
        success_count=success_count,
        inferred_succeeded=inferred_succeeded,
        child_numbers=child_numbers,
        failed_count=failed_count,
        unaccounted=unaccounted,
        failed_unknown_count=failed_unknown_count,
        partial_success_warning=None,
    )

    return cast(
        MutationResult,
        {
            "ok": outcome == "ok",
            "parent_number": parent_number,
            "outcome": outcome,
            "success_count": success_count,
            "failed_count": failed_count,
            "succeeded": succeeded,
            "failed": failed_serialized,
            "unaccounted": unaccounted,
            "failed_unknown_count": failed_unknown_count,
            "github_errors": github_errors,
            "partial_success_warning": partial_success_warning,
            "error": None,
        },
    )


def parse_subissue_child_node(node: JsonDict) -> SubIssueChild:
    assignees = [
        str(a["login"])
        for a in dict_nodes(as_dict(node.get("assignees")).get("nodes"))
        if a.get("login")
    ]
    pipeline_name: str | None = None
    pipeline_workspace_scoped = False
    pi = as_dict(node.get("pipelineIssue"))
    if pi:
        pl = as_dict(pi.get("pipeline"))
        name = pl.get("name")
        if name:
            pipeline_name = str(name)
            pipeline_workspace_scoped = True
    if not pipeline_name:
        fallback = dict_nodes(as_dict(node.get("pipelineIssues")).get("nodes"))
        if fallback:
            name = as_dict(fallback[0].get("pipeline")).get("name")
            if name:
                pipeline_name = str(name)

    repo = as_dict(node.get("repository"))
    number = node.get("number")
    issue_id = node.get("id")
    return {
        "id": str(issue_id) if issue_id is not None else "",
        "number": number if isinstance(number, int) and not isinstance(number, bool) else 0,
        "title": str(node.get("title") or ""),
        "state": str(node.get("state") or "UNKNOWN"),
        "pipeline": pipeline_name,
        "pipeline_workspace_scoped": pipeline_workspace_scoped,
        "assignees": assignees,
        "repository": {
            "owner": str(repo.get("ownerName") or ""),
            "name": str(repo.get("name") or ""),
        },
    }


def parse_sprint_issue_node(issue: JsonDict) -> SprintIssueRow:
    assignees = [
        str(a["login"])
        for a in dict_nodes(as_dict(issue.get("assignees")).get("nodes"))
        if a.get("login")
    ]
    pipeline_name: str | None = None
    scoped = as_dict(issue.get("pipelineIssue"))
    if scoped:
        name = as_dict(scoped.get("pipeline")).get("name")
        if name:
            pipeline_name = str(name)
    if not pipeline_name:
        pipeline_nodes = dict_nodes(as_dict(issue.get("pipelineIssues")).get("nodes"))
        if pipeline_nodes:
            name = as_dict(pipeline_nodes[0].get("pipeline")).get("name")
            if name:
                pipeline_name = str(name)
    rep = as_dict(issue.get("repository"))
    est = as_dict(issue.get("estimate")).get("value")
    number = issue.get("number")
    return {
        "number": number if isinstance(number, int) and not isinstance(number, bool) else 0,
        "title": str(issue.get("title") or ""),
        "state": str(issue.get("state") or "UNKNOWN"),
        "html_url": str(issue.get("htmlUrl") or ""),
        "estimate": float(est) if isinstance(est, (int, float)) and not isinstance(est, bool) else None,
        "assignees": assignees,
        "pipeline": pipeline_name,
        "repository": {
            "owner": str(rep.get("ownerName") or ""),
            "name": str(rep.get("name") or ""),
        },
    }


def remove_subissue_preflight_messages(
    *,
    not_found: list[int],
    cross_repo: list[CrossRepoChild],
    wrong_parent: list[WrongParentChild],
) -> str:
    msgs: list[str] = []
    if not_found:
        msgs.append("not found: " + ", ".join(f"#{n}" for n in not_found))
    if cross_repo:
        msgs.append("cross-repo: " + ", ".join(f"#{c['number']}→{c['owner']}/{c['name']}" for c in cross_repo))
    if wrong_parent:
        msgs.append(
            "wrong parent: "
            + ", ".join(
                f"#{w['number']} (actual parent: {'#' + str(w['actual_parent']) if w.get('actual_parent') else 'none'})"
                for w in wrong_parent
            )
        )
    return "Pre-flight validation failed: " + "; ".join(msgs)


def remove_subissue_preflight_failure_payload(
    *,
    parent_number: int,
    child_numbers: list[int],
    not_found: list[int],
    cross_repo: list[CrossRepoChild],
    wrong_parent: list[WrongParentChild],
) -> MutationResult:
    mismatch_numbers = set(not_found) | {c["number"] for c in cross_repo} | {w["number"] for w in wrong_parent}
    failed: list[FailedIssueRef | int] = [
        *[{"number": n, "owner": "", "name": ""} for n in not_found],
        *[{"number": c["number"], "owner": c["owner"], "name": c["name"]} for c in cross_repo],
        *[{"number": w["number"], "owner": "", "name": ""} for w in wrong_parent],
    ]
    return {
        "ok": False,
        "parent_number": parent_number,
        "outcome": "fail",
        "success_count": 0,
        "failed_count": (len(not_found) + len(wrong_parent) + len(cross_repo)),
        "succeeded": [],
        "failed": failed,
        "unaccounted": [n for n in child_numbers if n not in mismatch_numbers],
        "failed_unknown_count": 0,
        "github_errors": None,
        "partial_success_warning": None,
        "error": remove_subissue_preflight_messages(
            not_found=not_found,
            cross_repo=cross_repo,
            wrong_parent=wrong_parent,
        ),
    }
