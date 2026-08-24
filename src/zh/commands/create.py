"""Create issue command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from zh.api import ZhApiError
from zh.cli.context import get_state
from zh.cli.output import emit_create_links, emit_json, error, success
from zh.commands._duplicate_check import optional_duplicate_check, parse_related_issues
from zh.commands._issue_body import resolve_create_body
from zh.issue_ops import create_issue, parse_issue_number


def register(app: typer.Typer) -> None:
    app.command("create", help="Create a new ZenHub issue")(create_cmd)


def create_cmd(
    ctx: typer.Context,
    *,
    title: Annotated[str, typer.Argument(help="Issue title")],
    issue_type: Annotated[str | None, typer.Option("-t", "--type", help="Issue type")] = None,
    labels: Annotated[str | None, typer.Option("-l", "--labels", help="Comma-separated labels")] = None,
    assignee: Annotated[str | None, typer.Option("-a", "--assignee", help="GitHub assignee")] = None,
    pipeline: Annotated[str | None, typer.Option("-p", "--pipeline", help="Target pipeline")] = None,
    estimate: Annotated[str | None, typer.Option("-e", "--estimate", help="Story points")] = None,
    body: Annotated[str | None, typer.Option("-b", "--body", "--description", help="Issue body")] = None,
    body_file: Annotated[Path | None, typer.Option("-f", "--file", "--body-file", help="Read body from file")] = None,
    from_stdin: Annotated[bool, typer.Option("--stdin", help="Read body from stdin")] = False,
    parent: Annotated[str | None, typer.Option("--parent", help="Parent issue number")] = None,
    priority: Annotated[str | None, typer.Option("--priority", help="Priority name")] = None,
    confirm_create: Annotated[bool, typer.Option("--confirm-create", help="Bypass duplicate block")] = False,
    skip_duplicate_check: Annotated[bool, typer.Option("--skip-duplicate-check", help="Skip similarity pre-flight")] = False,
    related_issues: Annotated[str | None, typer.Option("--related-issues", help="Comma-separated structural-relative issue numbers")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="JSON on stdout")] = False,
    quiet: Annotated[bool, typer.Option("-q", "--quiet", help="Emit only the new issue number")] = False,
) -> None:
    """Create a new ZenHub issue."""
    state = get_state(ctx)
    ctx_obj = state.context()
    body_text = resolve_create_body(body=body, body_file=body_file, from_stdin=from_stdin)
    label_list = [x.strip() for x in labels.split(",")] if labels else None
    parent_num = parse_issue_number(parent) if parent else None
    related_nums = parse_related_issues(related_issues)

    dup_info = optional_duplicate_check(
        title=title,
        body=body_text,
        owner_repo=ctx_obj.owner_repo,
        parent=parent_num,
        related_issues=related_nums,
        skip=skip_duplicate_check,
    )
    if dup_info and dup_info.get("recommendation") == "block" and not confirm_create:
        payload = {
            "ok": False,
            "blocked": True,
            "duplicate_check": dup_info,
        }
        if json_output or state.json_output:
            emit_json(payload)
        else:
            error(
                "Refused: similar open issue exists. Review with `zh similar`, then retry with --confirm-create",
                exit_code=1,
            )

    try:
        created = create_issue(
            ctx_obj,
            title=title,
            body=body_text,
            issue_type=issue_type,
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
    success(f"Created issue #{created['number']}: {title}")
    emit_create_links(created)
