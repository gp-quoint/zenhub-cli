"""Discovery commands: board, pipelines, pipeline, workspaces, types, labels, users, mine."""

from __future__ import annotations

from typing import Annotated

import typer

from zh.api import ZhApiError, list_workspaces
from zh.cli.context import get_state
from zh.cli.color import paint
from zh.cli.formatting import format_board_overview_lines, format_mine_issues_list, format_pipeline_issues_table
from zh.cli.output import emit_json, error, info, print_line
from zh.gh_ops import gh_current_user, run_gh
from zh.schemas import PipelineIssueRow
from zh.workspace_ops import (
    board_overview,
    fetch_issue_types,
    fetch_labels,
    fetch_priorities,
    list_pipelines,
    pipeline_issues,
)

_BOARD_BAR_MAX = 30


def register(app: typer.Typer) -> None:
    app.command("board", help="Show board overview (issue count per pipeline)")(board_cmd)
    app.command("b", hidden=True)(board_cmd)
    app.command("overview", hidden=True)(board_cmd)
    app.command("pipelines", help="List pipeline names for the workspace")(pipelines_cmd)
    app.command("pipes", hidden=True)(pipelines_cmd)
    app.command("p", hidden=True)(pipelines_cmd)
    app.command("pipeline", help="List issues in a pipeline")(pipeline_cmd)
    app.command("pipe", hidden=True)(pipeline_cmd)
    app.command("col", hidden=True)(pipeline_cmd)
    app.command("workspaces", help="List workspaces connected to this repository")(workspaces_cmd)
    app.command("ws", hidden=True)(workspaces_cmd)
    app.command("types", help="List assignable issue types")(types_cmd)
    app.command("labels", help="List repository labels")(labels_cmd)
    app.command("priorities", help="List workspace priorities")(priorities_cmd)
    app.command("prios", hidden=True)(priorities_cmd)
    app.command("users", help="List assignable users (via gh collaborators)")(users_cmd)
    app.command("mine", help="List issues assigned to a user")(mine_cmd)
    app.command("my", hidden=True)(mine_cmd)


def board_cmd(
    ctx: typer.Context,
    all_issues: Annotated[bool, typer.Option("--all", "-a", help="Include closed issues")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
) -> None:
    """Show board overview (issue count per pipeline)."""
    state = get_state(ctx)
    ctx_obj = state.context()
    try:
        info(f"Getting board overview for {ctx_obj.owner_repo}...")
        data = board_overview(ctx_obj, include_closed=all_issues)
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, **data})
        return
    label = "total" if all_issues else "open"
    for line in format_board_overview_lines(
        workspace=str(data.get("workspace") or ""),
        total=int(data.get("total") or 0),
        label=label,
        pipelines=data["pipelines"],
        bar_max=_BOARD_BAR_MAX,
    ):
        print_line(line)


def pipelines_cmd(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List pipeline names for the workspace."""
    state = get_state(ctx)
    try:
        ctx_obj = state.context()
        pipes = list_pipelines(ctx_obj)
    except ZhApiError as exc:
        error(str(exc))
    names = [str(p.get("name") or "") for p in pipes if p.get("name")]
    if json_output or state.json_output:
        emit_json({"ok": True, "pipelines": names})
        return
    print_line("\n".join(names))


def pipeline_cmd(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Pipeline name")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List issues in a pipeline."""
    state = get_state(ctx)
    try:
        data = pipeline_issues(state.context(), name)
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, **data})
        return
    print_line(paint(f"\nPipeline: {data['pipeline']}\n", "bold"))
    for line in format_pipeline_issues_table(data["issues"]):
        print_line(line)


def workspaces_cmd(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List workspaces connected to this repository."""
    state = get_state(ctx)
    try:
        ctx_obj = state.context()
        rows = list_workspaces(ctx_obj.owner_repo)
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, "workspaces": rows})
        return
    for row in rows:
        marker = "●" if row.get("id") == ctx_obj.workspace_id else " "
        print_line(f"{marker} {row.get('name')}")


def types_cmd(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List assignable issue types."""
    state = get_state(ctx)
    try:
        rows = fetch_issue_types(state.context())
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, "types": rows})
        return
    for row in rows:
        print_line(
            f"{row.get('name'):<12} level={row.get('level')} disposition={row.get('disposition')} source={row.get('typename')}",
        )


def labels_cmd(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List repository labels."""
    state = get_state(ctx)
    try:
        rows = fetch_labels(state.context())
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, "labels": rows})
        return
    for row in rows:
        print_line(str(row.get("name") or ""))


def priorities_cmd(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List workspace priorities."""
    state = get_state(ctx)
    try:
        rows = fetch_priorities(state.context())
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, "priorities": rows})
        return
    for row in rows:
        print_line(f"{row.get('name')} ({row.get('color')})")


def users_cmd(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List assignable workspace users (via gh collaborators)."""
    state = get_state(ctx)
    owner_repo = state.context().owner_repo
    try:
        raw = run_gh(
            ["api", f"repos/{owner_repo}/collaborators", "--jq", ".[].login"],
            repo=None,
        )
        users = [line.strip() for line in raw.splitlines() if line.strip()]
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, "users": users})
        return
    print_line("\n".join(users))


def mine_cmd(
    ctx: typer.Context,
    user: Annotated[str | None, typer.Argument(help="GitHub username")] = None,
    no_urls: Annotated[bool, typer.Option("--no-urls")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List issues assigned to a user."""
    state = get_state(ctx)
    try:
        target = user.lstrip("@") if user else gh_current_user()
        info(f"Finding issues assigned to {target}...")
        ctx_obj = state.context()
        all_rows: list[PipelineIssueRow] = []
        for pipe in list_pipelines(ctx_obj):
            pname = str(pipe.get("name") or "")
            pid = str(pipe.get("id") or "")
            data = pipeline_issues(ctx_obj, pname, assignee=target, pipeline_id=pid)
            for issue in data["issues"]:
                issue["pipeline"] = pname
                all_rows.append(issue)

        def _mine_sort_key(row: PipelineIssueRow) -> tuple[str, int]:
            num = row.get("number")
            n = num if isinstance(num, int) else 0
            return (str(row.get("pipeline") or ""), n)

        all_rows.sort(key=_mine_sort_key)
    except ZhApiError as exc:
        error(str(exc))
    if json_output or state.json_output:
        emit_json({"ok": True, "user": target, "issues": all_rows})
        return
    print_line(paint(f"\nIssues assigned to {target} ({len(all_rows)}):\n", "bold"))
    for line in format_mine_issues_list(all_rows, include_urls=not no_urls):
        print_line(line)
    if all_rows:
        print_line("")
