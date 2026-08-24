"""Sub-issue commands (Typer sub-app: zh subissue …)."""

from __future__ import annotations

from typing import Annotated

import typer

from zh.api import ZhApiError
from zh.cli.context import get_state
from zh.cli.output import emit_json, error, print_line, success
from zh.graphql_ops import (
    add_sub_issues,
    list_sub_issues,
    remove_sub_issues,
    reorder_sub_issue,
)
from zh.issue_ops import parse_issue_number

app = typer.Typer(
    name="subissue",
    help="Sub-issue hierarchy: list, add, remove, reorder",
    no_args_is_help=True,
)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="subissue")
    root.add_typer(app, name="subissues", hidden=True)
    root.add_typer(app, name="sub", hidden=True)


@app.command("list", help="List sub-issues of a parent")
def list_cmd(
    ctx: typer.Context,
    parent: Annotated[str, typer.Argument(help="Parent issue number")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List sub-issues of a parent."""
    state = get_state(ctx)
    parent_num = parse_issue_number(parent)
    try:
        data = list_sub_issues(state.context(), parent_num)
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, **data})
        return
    print_line(f"\nSub-issues of #{parent_num}:\n")
    for child in data.get("children") or []:
        print_line(f"  #{child.get('number')} {child.get('title')}")


@app.command("add", help="Link issues as sub-issues")
def add_cmd(
    ctx: typer.Context,
    parent: Annotated[str, typer.Argument(help="Parent issue number")],
    children: Annotated[list[str], typer.Argument(help="Child issue numbers")],
) -> None:
    """Link issues as sub-issues."""
    state = get_state(ctx)
    parent_num = parse_issue_number(parent)
    child_nums = [parse_issue_number(c) for c in children]
    try:
        result = add_sub_issues(state.context(), parent_num, child_nums)
    except ZhApiError as exc:
        error(str(exc))
    if result.get("outcome") != "ok":
        error(str(result.get("message") or "add sub-issues failed"), exit_code=2)
    success(f"Added {result.get('success_count', 0)} sub-issue(s) under #{parent_num}")


@app.command("remove", help="Unlink sub-issues from a parent")
def remove_cmd(
    ctx: typer.Context,
    parent: Annotated[str, typer.Argument(help="Parent issue number")],
    children: Annotated[list[str], typer.Argument(help="Child issue numbers")],
) -> None:
    """Unlink sub-issues from a parent."""
    state = get_state(ctx)
    parent_num = parse_issue_number(parent)
    child_nums = [parse_issue_number(c) for c in children]
    try:
        result = remove_sub_issues(state.context(), parent_num, child_nums)
    except ZhApiError as exc:
        error(str(exc))
    if result.get("outcome") != "ok":
        error(str(result.get("message") or "remove sub-issues failed"), exit_code=2)
    success(f"Removed {result.get('success_count', 0)} sub-issue(s) from #{parent_num}")


@app.command("reorder", help="Reorder a sub-issue among siblings")
def reorder_cmd(
    ctx: typer.Context,
    child: Annotated[str, typer.Argument(help="Child issue number")],
    position: Annotated[str, typer.Argument(help="top|bottom|after N|before N")],
) -> None:
    """Reorder a sub-issue among siblings."""
    state = get_state(ctx)
    child_num = parse_issue_number(child)
    try:
        result = reorder_sub_issue(state.context(), child_num, position)
    except ZhApiError as exc:
        error(str(exc))
    if result.get("outcome") != "ok":
        error(str(result.get("message") or "reorder failed"), exit_code=2)
    success(f"Reordered #{child_num} to {position}")
