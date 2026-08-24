"""Issue lifecycle commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from zh.api import ZhApiError
from zh.cli.context import get_state
from zh.cli.default_command import DefaultCommandGroup
from zh.cli.output import emit_json, error, info, print_line, success, warn
from zh.commands._issue_body import (
    comment_body_for_edit,
    comment_body_or_editor,
    resolve_comment_edit_target,
    resolve_issue_edit_fields,
)
from zh.deps_ops import create_blockage, remove_blockage
from zh.gh_ops import (
    gh_current_user,
    gh_edit_comment,
    gh_fetch_issue_comments,
    gh_issue_close,
    gh_issue_comment,
    gh_issue_delete,
    gh_issue_reopen,
    gh_issue_view,
    open_issue_url,
)
from zh.graphql_ops import get_issue_by_info, list_sub_issues
from zh.issue_ops import (
    assign_issue,
    move_issue,
    parse_issue_number,
    reorder_issue,
    set_estimate,
    set_issue_type,
    set_priority,
    unassign_issue,
    update_issue,
)

comment_app = typer.Typer(
    name="comment",
    help="Add or edit issue comments",
    cls=DefaultCommandGroup,
    no_args_is_help=True,
)


def register(app: typer.Typer) -> None:
    app.command("issue", help="View issue details")(issue_cmd)
    app.command("i", hidden=True)(issue_cmd)
    app.command("show", hidden=True)(issue_cmd)
    app.command("move", help="Move an issue to a pipeline")(move_cmd)
    app.command("mv", hidden=True)(move_cmd)
    app.command("m", hidden=True)(move_cmd)
    app.command("reorder", help="Reorder an issue within its pipeline")(reorder_cmd)
    app.command("order", hidden=True)(reorder_cmd)
    app.command("pos", hidden=True)(reorder_cmd)
    app.command("estimate", help="Set story point estimate")(estimate_cmd)
    app.command("est", hidden=True)(estimate_cmd)
    app.command("points", hidden=True)(estimate_cmd)
    app.command("assign", help="Assign user(s) to an issue")(assign_cmd)
    app.command("unassign", help="Remove assignee(s) from an issue")(unassign_cmd)
    app.command("priority", help="Set workspace priority by name")(priority_cmd)
    app.command("prio", hidden=True)(priority_cmd)
    app.command("type", help="Change an issue's type")(type_cmd)
    app.command("set-type", hidden=True)(type_cmd)
    app.command("retype", hidden=True)(type_cmd)
    app.add_typer(comment_app, name="comment")
    app.command("c", hidden=True)(comment_add_cmd)
    app.command("edit", help="Edit issue title/description")(edit_cmd)
    app.command("e", hidden=True)(edit_cmd)
    app.command("attach", help="Open issue in browser for file attachments")(attach_cmd)
    app.command("block", help="Set dependency: blocked is blocked by blocker")(block_cmd)
    app.command("unblock", help="Remove dependency (requires ZH_REST_TOKEN)")(unblock_cmd)
    app.command("close", help="Close an issue")(close_cmd)
    app.command("reopen", help="Reopen a closed issue")(reopen_cmd)
    app.command("delete", help="Permanently delete a GitHub issue (danger)")(delete_cmd)


def issue_cmd(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="Issue number")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """View issue details via GitHub."""
    state = get_state(ctx)
    ctx_obj = state.context()
    num = parse_issue_number(number)
    try:
        data = gh_issue_view(ctx_obj.owner_repo, num)
        subs = list_sub_issues(ctx_obj, num)
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, "issue": data, "sub_issues": subs.get("children", [])})
        return
    print_line(f"\n#{num}: {data.get('title')}\n")
    print_line(str(data.get("body") or ""))
    print_line(f"\nState: {data.get('state')}  URL: {data.get('url')}")
    children = subs.get("children") or []
    if children:
        print_line(f"\nSub-issues ({len(children)}):")
        for child in children:
            print_line(f"  #{child.get('number')} {child.get('title')}")


def move_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
    pipeline: Annotated[str, typer.Argument(help="Target pipeline name")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Move an issue to a pipeline."""
    state = get_state(ctx)
    num = parse_issue_number(issue)
    try:
        result = move_issue(state.context(), num, pipeline)
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json(
            {
                "ok": True,
                "number": int(result["number"]),
                "title": result["title"],
                "from": result["from_pipeline"],
                "to": result["to_pipeline"],
            }
        )
        return
    success(f"Moved issue #{result['number']}: {result['title']}")
    print_line(f"  {result['from_pipeline']} → {result['to_pipeline']}")


def reorder_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
    position: Annotated[str, typer.Argument(help="Position, top, or bottom")],
) -> None:
    """Reorder an issue within its current pipeline."""
    state = get_state(ctx)
    num = parse_issue_number(issue)
    try:
        result = reorder_issue(state.context(), num, position)
    except ZhApiError as exc:
        error(str(exc))
    success(f"Reordered issue #{result['number']}: {result['title']}")
    print_line(f"  Now at position {result['position']}")


def estimate_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
    points: Annotated[str, typer.Argument(help="Points or 'clear'")],
) -> None:
    """Set story point estimate."""
    state = get_state(ctx)
    num = parse_issue_number(issue)
    try:
        applied = set_estimate(state.context(), num, points)
    except ZhApiError as exc:
        error(str(exc))
    success(f"Set estimate on #{num} to {applied!r}")


def assign_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
    users: Annotated[list[str], typer.Argument(help="GitHub username(s)")],
) -> None:
    """Assign one or more users to an issue."""
    state = get_state(ctx)
    num = parse_issue_number(issue)
    try:
        result = assign_issue(state.context(), num, users)
    except ZhApiError as exc:
        error(str(exc))
    if result.get("already_assigned"):
        already = result.get("already_assigned") or []
        success(f"{', '.join(already)} already assigned to #{num}: {result['title']}")
        print_line(f"  Assignees: {', '.join(result['assignees'])}")
        return
    added = result.get("added") or []
    success(f"Assigned {', '.join(added)} to #{num}: {result['title']}")
    print_line(f"  Assignees: {', '.join(result['assignees'])}")


def unassign_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
    users: Annotated[list[str] | None, typer.Argument(help="Username(s) to remove")] = None,
    clear_all: Annotated[bool, typer.Option("--all", help="Remove all assignees")] = False,
) -> None:
    """Remove assignee(s) from an issue."""
    state = get_state(ctx)
    num = parse_issue_number(issue)
    try:
        result = unassign_issue(state.context(), num, users or [], clear_all=clear_all)
    except ZhApiError as exc:
        error(str(exc))
    if clear_all:
        success(f"Removed all assignees from #{num}: {result['title']}")
    else:
        success(f"Removed {result.get('removed', '?')} from #{num}: {result['title']}")
    remaining = ", ".join(result["assignees"]) or "none"
    print_line(f"  Assignees: {remaining}")


def priority_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
    level: Annotated[str, typer.Argument(help="Priority name or 'clear'")],
) -> None:
    """Set workspace priority by name."""
    state = get_state(ctx)
    num = parse_issue_number(issue)
    try:
        applied = set_priority(state.context(), num, level)
    except ZhApiError as exc:
        error(str(exc))
    success(f"Set priority on #{num} to {applied!r}")


def type_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
    issue_type: Annotated[str, typer.Argument(help="Issue type name")],
) -> None:
    """Change an issue's type."""
    state = get_state(ctx)
    num = parse_issue_number(issue)
    try:
        applied = set_issue_type(state.context(), num, issue_type)
    except ZhApiError as exc:
        error(str(exc))
    success(f"Changed #{num} type to {applied}")


@comment_app.command("add", help="Add a comment (default when no subcommand is given)")
def comment_add_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
    text: Annotated[str | None, typer.Argument(help="Comment text")] = None,
    message: Annotated[str | None, typer.Option("-m", "--message", help="Comment text")] = None,
    body_file: Annotated[Path | None, typer.Option("-f", "--file", help="Read comment from file")] = None,
    from_stdin: Annotated[bool, typer.Option("--stdin", help="Read comment from stdin")] = False,
) -> None:
    """Add a comment (opens $EDITOR when no body is given)."""
    state = get_state(ctx)
    num = parse_issue_number(issue)
    body = comment_body_or_editor(message, body_file, from_stdin=from_stdin, positional=text)
    if body is None:
        info("empty buffer — cancelled")
        return
    if not body.strip():
        error("comment body is required. use -m, -f, --stdin, or provide text as an argument.")
    try:
        gh_issue_comment(state.context().owner_repo, num, body)
    except ZhApiError as exc:
        error(str(exc))
    success(f"Added comment to #{num}")


@comment_app.command("edit", help="Edit one of your comments")
def comment_edit_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
    index: Annotated[int | None, typer.Argument(help="1-based comment index from zh issue")] = None,
    message: Annotated[str | None, typer.Option("-m", "--message", help="Replacement comment text")] = None,
    body_file: Annotated[Path | None, typer.Option("-f", "--file", help="Read replacement from file")] = None,
    from_stdin: Annotated[bool, typer.Option("--stdin", help="Read replacement from stdin")] = False,
    fills: Annotated[
        list[str] | None,
        typer.Option(
            "--fill",
            help="Replace {{KEY}} in the body with value (KEY=value). Repeatable. Uses existing body when no -m/-f/--stdin.",
        ),
    ] = None,
) -> None:
    """Edit one of YOUR comments on an issue.

    Non-interactive: pass -m / -f / --stdin, and/or --fill KEY=value for deferred
    placeholder fill (e.g. after PR URLs are known). Bare invocation opens $EDITOR.
    """
    state = get_state(ctx)
    num = parse_issue_number(issue)
    owner_repo = state.context().owner_repo
    try:
        me = gh_current_user()
        comments = gh_fetch_issue_comments(owner_repo, num)
    except ZhApiError as exc:
        error(str(exc))
    try:
        idx, comment_id, old_body = resolve_comment_edit_target(comments, index=index, me=me, issue_num=num)
    except SystemExit:
        return
    new_body = comment_body_for_edit(
        old_body,
        message,
        body_file,
        from_stdin=from_stdin,
        fills=fills or [],
    )
    if new_body is None:
        info("empty buffer — cancelled")
        return
    if new_body.rstrip("\n") == old_body.rstrip("\n"):
        info("unchanged — skipped")
        return
    try:
        gh_edit_comment(owner_repo, comment_id, new_body)
    except ZhApiError as exc:
        error(str(exc))
    success(f"Updated comment {idx} on #{num}")


def edit_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
    *,
    title: Annotated[str | None, typer.Option("-t", "--title", help="New title")] = None,
    description: Annotated[str | None, typer.Option("-d", "--description", "-b", "--body", help="New body")] = None,
    body_file: Annotated[Path | None, typer.Option("-f", "--file", "--body-file", help="Read body from file")] = None,
    from_stdin: Annotated[bool, typer.Option("--stdin", help="Read body from stdin")] = False,
) -> None:
    """Edit issue title and/or description."""
    state = get_state(ctx)
    num = parse_issue_number(issue)
    ctx_obj = state.context()
    try:
        zh_issue = gh_issue_view(ctx_obj.owner_repo, num)
        zh_node = get_issue_by_info(ctx_obj, num)
    except ZhApiError as exc:
        error(str(exc))
    if zh_node is None:
        error(f"Issue #{num} not found")
    old_title = str(zh_issue.get("title") or "")
    old_body = str(zh_issue.get("body") or "")
    resolved = resolve_issue_edit_fields(
        title=title,
        description=description,
        body_file=body_file,
        from_stdin=from_stdin,
        old_title=old_title,
        old_body=old_body,
    )
    if resolved is None:
        return
    new_title, new_body = resolved
    title_changed = new_title is not None and new_title != old_title
    body_changed = new_body is not None and new_body.rstrip("\n") != old_body.rstrip("\n")
    if not title_changed and not body_changed:
        if new_title is None and new_body is None:
            error("nothing to update: provide -t (title) and/or -d (description).")
        info("unchanged — skipped")
        return
    try:
        result = update_issue(
            ctx_obj,
            num,
            title=new_title if title_changed else None,
            body=new_body if body_changed else None,
        )
    except ZhApiError as exc:
        error(str(exc))
    success(f"Updated #{result['number']}: {result['title']}")


def attach_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
) -> None:
    """Open the issue in a browser for drag-and-drop attachments."""
    state = get_state(ctx)
    num = parse_issue_number(issue)
    url = open_issue_url(state.context().owner_repo, num)
    info(f"Opening issue #{num} in browser for attachment upload...")
    warn("GitHub's API does not support file uploads to issues; drag and drop in the browser.")
    print_line(f"  URL: {url}")


def block_cmd(
    ctx: typer.Context,
    blocked: Annotated[str, typer.Argument(help="Blocked issue number")],
    blocking: Annotated[str, typer.Argument(help="Blocking issue number")],
) -> None:
    """Set dependency: blocked is blocked by blocking."""
    state = get_state(ctx)
    try:
        result = create_blockage(state.context(), parse_issue_number(blocked), parse_issue_number(blocking))
    except ZhApiError as exc:
        error(str(exc))
    success("Created dependency")
    print_line(f"  #{result['blocked']} ({result['blocked_title']})")
    print_line("  is blocked by")
    print_line(f"  #{result['blocking']} ({result['blocking_title']})")


def unblock_cmd(
    ctx: typer.Context,
    blocked: Annotated[str, typer.Argument(help="Blocked issue number")],
    blocking: Annotated[str, typer.Argument(help="Blocking issue number")],
) -> None:
    """Remove dependency (requires ZH_REST_TOKEN)."""
    state = get_state(ctx)
    try:
        remove_blockage(state.context().owner_repo, blocked, blocking)
    except ZhApiError as exc:
        error(str(exc))
    success(f"Removed dependency: #{parse_issue_number(blocked)} is no longer blocked by #{parse_issue_number(blocking)}")


def close_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
    comment: Annotated[str | None, typer.Argument(help="Optional closing comment")] = None,
    reason: Annotated[str, typer.Option("-r", "--reason", help="completed|not planned|duplicate")] = "completed",
) -> None:
    """Close an issue."""
    state = get_state(ctx)
    num = parse_issue_number(issue)
    try:
        gh_issue_close(state.context().owner_repo, num, comment=comment or "", reason=reason)
    except ZhApiError as exc:
        error(str(exc))
    success(f"Closed #{num}")


def reopen_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
) -> None:
    """Reopen a closed issue."""
    state = get_state(ctx)
    num = parse_issue_number(issue)
    try:
        gh_issue_reopen(state.context().owner_repo, num)
    except ZhApiError as exc:
        error(str(exc))
    success(f"Reopened #{num}")


def delete_cmd(
    ctx: typer.Context,
    issue: Annotated[str, typer.Argument(help="Issue number")],
    yes: Annotated[bool, typer.Option("-y", "--yes", help="Skip confirmation")] = False,
) -> None:
    """Permanently delete a GitHub issue (danger)."""
    state = get_state(ctx)
    num = parse_issue_number(issue)
    if not yes:
        error("Refusing to delete without -y/--yes (permanent)")
    try:
        gh_issue_delete(state.context().owner_repo, num)
    except ZhApiError as exc:
        error(str(exc))
    success(f"Deleted #{num}")
