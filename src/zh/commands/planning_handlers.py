"""Planning noun command implementations (shared by epic/initiative/project/subtask)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer

from zh.api import ZhApiError
from zh.cli.output import emit_create_links, emit_json, error, print_line, success, warn
from zh.commands._duplicate_check import optional_duplicate_check
from zh.commands._issue_body import resolve_create_body
from zh.gh_ops import gh_issue_close, gh_issue_reopen, gh_issue_view
from zh.graphql_ops import add_sub_issues, remove_sub_issues
from zh.issue_ops import create_issue, parse_issue_number, update_issue
from zh.planning_ops import (
    ensure_type_for_create,
    list_issues_by_type,
    show_planning_issue,
    warn_type_mismatch,
)

if TYPE_CHECKING:
    from zh.cli.state import CliState


def run_noun_create(
    state: CliState,
    *,
    type_name: str,
    cmd_name: str,
    title: str,
    description: str | None,
    body_file: Path | None,
    from_stdin: bool,
    labels: str | None,
    assignee: str | None,
    pipeline: str | None,
    estimate: str | None,
    parent: str | None,
    priority: str | None,
    confirm_create: bool,
    skip_duplicate_check: bool,
    related_issues: list[int] | None,
    json_output: bool,
    quiet: bool,
    issue_type_flag: str | None,
) -> None:
    if issue_type_flag:
        error(
            f"-t conflicts with the noun type {type_name}. Use 'zh create -t <type>' or 'zh type <issue#> <name>' instead.",
        )
    ctx_obj = state.context()
    try:
        ensure_type_for_create(ctx_obj, type_name)
    except ZhApiError as exc:
        error(str(exc))
    body_text = resolve_create_body(
        body=None,
        description=description,
        body_file=body_file,
        from_stdin=from_stdin,
    )
    label_list = [x.strip() for x in labels.split(",")] if labels else None
    parent_num = parse_issue_number(parent) if parent else None
    dup_info = optional_duplicate_check(
        title=title,
        body=body_text,
        owner_repo=ctx_obj.owner_repo,
        parent=parent_num,
        related_issues=related_issues,
        skip=skip_duplicate_check,
    )
    if dup_info and dup_info.get("recommendation") == "block" and not confirm_create:
        payload = {"ok": False, "blocked": True, "duplicate_check": dup_info}
        if json_output or state.json_output:
            emit_json(payload)
        else:
            error("Refused: similar open issue exists. Review with `zh similar`, then retry with --confirm-create")
    try:
        created = create_issue(
            ctx_obj,
            title=title,
            body=body_text,
            issue_type=type_name,
            labels=label_list,
            assignee=assignee,
            pipeline=pipeline,
            estimate=estimate,
            parent_number=parent_num,
            priority_name=priority,
        )
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, "duplicate_check": dup_info, **created})
        return
    if quiet:
        typer.echo(str(created["number"]))
        return
    success(f"Created {cmd_name} #{created['number']}: {title}")
    emit_create_links(created)


def run_noun_list(state: CliState, *, type_name: str, cmd_name: str, extra: list[str] | None, json_output: bool) -> None:
    if extra:
        error(
            f"zh {cmd_name} list takes no arguments (got {len(extra)} extra). "
            f"Did you mean 'zh subissue list <parent#>' or 'zh {cmd_name} show <issue#>'?",
        )
    try:
        data = list_issues_by_type(state.context(), type_name)
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        payload = {"ok": True, **data}
        if cmd_name == "epic":
            payload["epics"] = data["items"]
        emit_json(payload)
        return
    print_line(f"\n{data['type']} issues in {data['workspace']} ({data['total_count']} total)\n")
    if not data["items"]:
        print_line(f"  No {data['type']} issues in this workspace\n")
        return
    for item in data["items"]:
        print_line(f"  #{item.get('number'):<5} {item.get('state'):<6} {item.get('title')}")
    if data["total_count"] > data["fetched_count"]:
        warn(f"Showing first {data['fetched_count']} of {data['total_count']} (query caps at 100).")
    print_line("")


def run_noun_show(state: CliState, *, type_name: str, issue: str, json_output: bool) -> None:
    num = parse_issue_number(issue)
    ctx_obj = state.context()
    try:
        gh = gh_issue_view(ctx_obj.owner_repo, num)
        data = show_planning_issue(ctx_obj, type_name, num)
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, "issue": gh, **data})
        return
    print_line(f"\n#{num}: {gh.get('title')}\n")
    print_line(str(gh.get("body") or ""))
    print_line(f"\nState: {gh.get('state')}  URL: {gh.get('url')}")
    print_line(f"\nChildren ({data.get('total_count', 0)}):\n")
    for child in data.get("children") or []:
        assignees = ", ".join(child.get("assignees") or []) or "unassigned"
        print_line(f"  #{child.get('number')} │ {child.get('pipeline', '-'):<18} │ {assignees:<15} │ {child.get('title')}")
    if (data.get("total_count") or 0) > (data.get("fetched_count") or 0):
        warn(
            f"Showing first {data.get('fetched_count')} of {data.get('total_count')} children "
            f"(query caps at 100). Use 'zh subissue list {num}' for the full set.",
        )
    print_line("")


def run_noun_add(state: CliState, *, parent: str, children: list[str]) -> None:
    parent_num = parse_issue_number(parent)
    child_nums = [parse_issue_number(c) for c in children]
    try:
        result = add_sub_issues(state.context(), parent_num, child_nums)
    except ZhApiError as exc:
        error(str(exc))
    if result.get("outcome") != "ok":
        error(str(result.get("message") or "add sub-issues failed"), exit_code=2)
    success(f"Added {result.get('success_count', 0)} sub-issue(s) under #{parent_num}")


def run_noun_remove(state: CliState, *, parent: str, children: list[str]) -> None:
    parent_num = parse_issue_number(parent)
    child_nums = [parse_issue_number(c) for c in children]
    try:
        result = remove_sub_issues(state.context(), parent_num, child_nums)
    except ZhApiError as exc:
        error(str(exc))
    if result.get("outcome") != "ok":
        error(str(result.get("message") or "remove sub-issues failed"), exit_code=2)
    success(f"Removed {result.get('success_count', 0)} sub-issue(s) from #{parent_num}")


def run_noun_update(state: CliState, *, type_name: str, issue: str, title: str | None, description: str | None) -> None:
    num = parse_issue_number(issue)
    ctx_obj = state.context()
    warn_type_mismatch(ctx_obj, type_name, num, "update")
    if title is None and description is None:
        error("Nothing to update: provide -t (title) and/or -d (description).")
    try:
        result = update_issue(ctx_obj, num, title=title, body=description)
    except ZhApiError as exc:
        error(str(exc))
    success(f"Updated #{result['number']}: {result['title']}")


def run_noun_close(state: CliState, *, type_name: str, issue: str, comment: str | None, reason: str) -> None:
    num = parse_issue_number(issue)
    ctx_obj = state.context()
    warn_type_mismatch(ctx_obj, type_name, num, "close")
    try:
        gh_issue_close(ctx_obj.owner_repo, num, comment=comment or "", reason=reason)
    except ZhApiError as exc:
        error(str(exc))
    success(f"Closed #{num}")


def run_noun_reopen(state: CliState, *, type_name: str, issue: str) -> None:
    num = parse_issue_number(issue)
    ctx_obj = state.context()
    warn_type_mismatch(ctx_obj, type_name, num, "reopen")
    try:
        gh_issue_reopen(ctx_obj.owner_repo, num)
    except ZhApiError as exc:
        error(str(exc))
    success(f"Reopened #{num}")


def run_noun_delete(*, type_name: str, cmd_name: str) -> None:
    error(
        f"'zh {cmd_name} delete' is no longer a verb ({type_name} is a normal issue). "
        f"Use 'zh delete <issue#>' instead (DANGER: irreversible; prefer 'zh {cmd_name} close <issue#>').",
    )
