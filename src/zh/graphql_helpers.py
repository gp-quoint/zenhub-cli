"""Shared GraphQL response parsing helpers for sub-issue mutations."""

from __future__ import annotations

from typing import Any

from zh.schemas import MutationResult


def serialize_failed_issues(failed_issues: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "number": (fi.get("number") if isinstance(fi, dict) else None),
            "owner": ((fi.get("repository") or {}).get("ownerName") or "" if isinstance(fi, dict) else ""),
            "name": ((fi.get("repository") or {}).get("name") or "" if isinstance(fi, dict) else ""),
        }
        for fi in failed_issues
    ]


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
    payload: dict[str, Any],
    classify_outcome: Any,
) -> MutationResult:
    success_count = int(payload.get("successCount") or 0)
    failed_issues = payload.get("failedIssues") or []
    failed_count = len(failed_issues)
    github_errors = payload.get("githubErrors") or None
    if isinstance(github_errors, dict) and not github_errors:
        github_errors = None

    failed_serialized = serialize_failed_issues(failed_issues)
    failed_numbers = {fi["number"] for fi in failed_serialized if isinstance(fi.get("number"), int) and not isinstance(fi.get("number"), bool)}
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

    return {
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
    }


def parse_subissue_child_node(node: dict[str, Any]) -> dict[str, Any]:
    assignees = [a.get("login") for a in ((node.get("assignees") or {}).get("nodes") or []) if a.get("login")]
    pipeline_name = None
    pipeline_workspace_scoped = False
    pi = node.get("pipelineIssue") or None
    if pi:
        pl = pi.get("pipeline") or {}
        pipeline_name = pl.get("name") or None
        if pipeline_name:
            pipeline_workspace_scoped = True
    if not pipeline_name:
        fallback_nodes = (node.get("pipelineIssues") or {}).get("nodes") or []
        if fallback_nodes:
            fp = (fallback_nodes[0] or {}).get("pipeline") or {}
            pipeline_name = fp.get("name") or None

    repo = node.get("repository") or {}
    return {
        "id": node.get("id"),
        "number": node.get("number"),
        "title": node.get("title") or "",
        "state": node.get("state") or "UNKNOWN",
        "pipeline": pipeline_name,
        "pipeline_workspace_scoped": pipeline_workspace_scoped,
        "assignees": assignees,
        "repository": {
            "owner": repo.get("ownerName") or "",
            "name": repo.get("name") or "",
        },
    }


def subissue_pagination_warning(page_info: dict[str, Any], last_cursor: str | None) -> str | None:
    has_next = bool(page_info.get("hasNextPage"))
    end_cursor = page_info.get("endCursor")
    if not has_next:
        return None
    if not end_cursor or end_cursor == last_cursor:
        return "Pagination cursor not advancing across requests — server likely mis-reporting hasNextPage. Bailing."
    return None


def parse_sprint_issue_node(issue: dict[str, Any]) -> dict[str, Any]:
    assignees = [a.get("login") for a in ((issue.get("assignees") or {}).get("nodes") or []) if a.get("login")]
    pipeline_name = None
    scoped = issue.get("pipelineIssue") or {}
    if isinstance(scoped, dict):
        pl = scoped.get("pipeline") or {}
        pipeline_name = pl.get("name") or None
    if not pipeline_name:
        pipeline_nodes = ((issue.get("pipelineIssues") or {}).get("nodes")) or []
        if pipeline_nodes:
            first_pn = pipeline_nodes[0] or {}
            pl = first_pn.get("pipeline") or {}
            pipeline_name = pl.get("name") or None
    rep = issue.get("repository") or {}
    est = issue.get("estimate") or {}
    return {
        "number": issue.get("number"),
        "title": issue.get("title") or "",
        "state": issue.get("state") or "UNKNOWN",
        "html_url": issue.get("htmlUrl") or "",
        "estimate": est.get("value"),
        "assignees": assignees,
        "pipeline": pipeline_name,
        "repository": {
            "owner": rep.get("ownerName") or "",
            "name": rep.get("name") or "",
        },
    }


def remove_subissue_preflight_messages(
    *,
    not_found: list[int],
    cross_repo: list[dict[str, Any]],
    wrong_parent: list[dict[str, Any]],
) -> str:
    msgs: list[str] = []
    if not_found:
        msgs.append("not found: " + ", ".join(f"#{n}" for n in not_found))
    if cross_repo:
        msgs.append("cross-repo: " + ", ".join(f"#{c['number']}→{c['owner']}/{c['name']}" for c in cross_repo))
    if wrong_parent:
        msgs.append(
            "wrong parent: "
            + ", ".join(f"#{w['number']} (actual parent: {'#' + str(w['actual_parent']) if w['actual_parent'] else 'none'})" for w in wrong_parent)
        )
    return "Pre-flight validation failed: " + "; ".join(msgs)


def remove_subissue_preflight_failure_payload(
    *,
    parent_number: int,
    child_numbers: list[int],
    not_found: list[int],
    cross_repo: list[dict[str, Any]],
    wrong_parent: list[dict[str, Any]],
) -> MutationResult:
    mismatch_numbers = set(not_found) | {c["number"] for c in cross_repo} | {w["number"] for w in wrong_parent}
    return {
        "ok": False,
        "parent_number": parent_number,
        "outcome": "fail",
        "success_count": 0,
        "failed_count": (len(not_found) + len(wrong_parent) + len(cross_repo)),
        "succeeded": [],
        "failed": [
            *[{"number": n, "owner": "", "name": ""} for n in not_found],
            *cross_repo,
            *[{"number": w["number"], "owner": "", "name": ""} for w in wrong_parent],
        ],
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
