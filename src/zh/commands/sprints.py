"""Sprint commands (Typer sub-app: zh sprint …)."""

from __future__ import annotations

from typing import Annotated

import typer

from zh.api import ZhApiError
from zh.cli.context import get_state
from zh.cli.color import paint
from zh.cli.default_command import DefaultCommandGroup
from zh.cli.formatting import sprint_heading
from zh.cli.output import emit_json, error, print_line, success
from zh.graphql_ops import (
    add_issues_to_sprint,
    get_current_sprint,
    get_sprint_detail,
    list_sprints,
    remove_issues_from_sprint,
)
from zh.issue_ops import parse_issue_number
from zh.types import sprint_key


class SprintCommandGroup(DefaultCommandGroup):
    """Default unknown first token to ``show`` so ``zh sprint current`` still works.

    Subcommands ``add`` / ``remove`` keep natural agent order:
    ``zh sprint add current 42`` (not ``zh sprint current add current 42``).
    """

    default_command = "show"


app = typer.Typer(
    name="sprint",
    help="Sprint membership: show, add, remove",
    cls=SprintCommandGroup,
    invoke_without_command=True,
    no_args_is_help=False,
)


def register(root: typer.Typer) -> None:
    root.command("sprints", help="List sprints in the workspace")(sprints_cmd)
    root.command("sp", hidden=True)(sprints_cmd)
    root.add_typer(app, name="sprint")
    root.command("sa", hidden=True)(sprint_add_alias)
    root.command("sr", hidden=True)(sprint_remove_alias)


def sprints_cmd(
    ctx: typer.Context,
    include_closed: Annotated[bool, typer.Option("--all", help="Include closed sprints")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List sprints in the workspace."""
    state = get_state(ctx)
    try:
        data = list_sprints(state.context(), include_closed=include_closed)
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, **data})
        return
    for sprint in data.get("sprints") or []:
        if sprint.get("active"):
            marker = paint("●", "green bold")
        else:
            marker = " "
        print_line(f"{marker} {sprint.get('name')}")


def _emit_sprint_detail(ctx: typer.Context, name: str | None, *, json_output: bool) -> None:
    state = get_state(ctx)
    ctx_obj = state.context()
    try:
        resolved = sprint_key(name)
        data = get_current_sprint(ctx_obj) if resolved == "current" else get_sprint_detail(ctx_obj, resolved)
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, **data})
        return
    print_line(f"\n{sprint_heading(data.get('sprint_name') or data.get('name'))}\n")
    for issue in data.get("issues") or []:
        num = issue.get("number")
        title = issue.get("title") or ""
        print_line(f"  {paint(f'#{num}', 'cyan bold')} {title}")


@app.callback()
def sprint_root(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show current sprint when invoked with no subcommand."""
    if ctx.invoked_subcommand is not None:
        return
    _emit_sprint_detail(ctx, "current", json_output=json_output)


@app.command("show", help="Show sprint detail (defaults to current/active)")
def sprint_show_cmd(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Sprint name or current/active (default: current)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show sprint detail."""
    _emit_sprint_detail(ctx, name, json_output=json_output)


@app.command("add", help="Add issues to a sprint")
def sprint_add_cmd(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Sprint name or current/active")],
    issues: Annotated[list[str], typer.Argument(help="Issue numbers")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Add issues to a sprint."""
    state = get_state(ctx)
    nums = [parse_issue_number(i) for i in issues]
    sprint_name = sprint_key(name)
    try:
        result = add_issues_to_sprint(state.context(), sprint_name, nums)
    except ZhApiError as exc:
        error(str(exc))
    if result.get("outcome") != "ok":
        error(str(result.get("message") or "sprint add failed"), exit_code=2)
    if json_output or state.json_output:
        emit_json(
            {
                "ok": True,
                "sprint": sprint_name,
                "issues": nums,
                "success_count": result.get("success_count", 0),
                "outcome": result.get("outcome"),
                "message": result.get("message"),
            }
        )
        return
    success(f"Added {result.get('success_count', 0)} issue(s) to sprint")


@app.command("remove", help="Remove issues from a sprint")
def sprint_remove_cmd(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Sprint name or current/active")],
    issues: Annotated[list[str], typer.Argument(help="Issue numbers")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Remove issues from a sprint."""
    state = get_state(ctx)
    nums = [parse_issue_number(i) for i in issues]
    sprint_name = sprint_key(name)
    try:
        result = remove_issues_from_sprint(state.context(), sprint_name, nums)
    except ZhApiError as exc:
        error(str(exc))
    if result.get("outcome") != "ok":
        error(str(result.get("message") or "sprint remove failed"), exit_code=2)
    if json_output or state.json_output:
        emit_json(
            {
                "ok": True,
                "sprint": sprint_name,
                "issues": nums,
                "success_count": result.get("success_count", 0),
                "outcome": result.get("outcome"),
                "message": result.get("message"),
            }
        )
        return
    success(f"Removed {result.get('success_count', 0)} issue(s) from sprint")


def sprint_add_alias(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Sprint name or current/active")],
    issues: Annotated[list[str], typer.Argument(help="Issue numbers")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Top-level alias for `zh sprint add`."""
    sprint_add_cmd(ctx, name, issues, json_output=json_output)


def sprint_remove_alias(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Sprint name or current/active")],
    issues: Annotated[list[str], typer.Argument(help="Issue numbers")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Top-level alias for `zh sprint remove`."""
    sprint_remove_cmd(ctx, name, issues, json_output=json_output)
