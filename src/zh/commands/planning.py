"""Planning-hierarchy commands: epic, initiative, project, subtask."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from zh.cli.context import get_state
from zh.commands._duplicate_check import parse_related_issues
from zh.commands.planning_handlers import (
    run_noun_add,
    run_noun_close,
    run_noun_create,
    run_noun_delete,
    run_noun_list,
    run_noun_remove,
    run_noun_reopen,
    run_noun_show,
    run_noun_update,
)

_NOUNS: tuple[tuple[str, str], ...] = (
    ("Initiative", "initiative"),
    ("Project", "project"),
    ("Epic", "epic"),
    ("Sub-task", "subtask"),
)


def register(root: typer.Typer) -> None:
    for type_name, cmd_name in _NOUNS:
        app = _make_noun_app(type_name, cmd_name)
        root.add_typer(app, name=cmd_name)
        if cmd_name == "epic":
            root.add_typer(app, name="epics", hidden=True)
        elif cmd_name == "initiative":
            root.add_typer(app, name="initiatives", hidden=True)
        elif cmd_name == "project":
            root.add_typer(app, name="projects", hidden=True)
        elif cmd_name == "subtask":
            for alias in ("subtasks", "sub-task", "sub-tasks"):
                root.add_typer(app, name=alias, hidden=True)


def _register_create(app: typer.Typer, type_name: str, cmd_name: str) -> None:
    @app.command("create", help=f"Create an issue with type {type_name}")
    def create_cmd(
        ctx: typer.Context,
        *,
        title: Annotated[str, typer.Argument(help="Issue title")],
        description: Annotated[str | None, typer.Option("-d", "--description", help="Issue body")] = None,
        body_file: Annotated[Path | None, typer.Option("-f", "--file", "--body-file", help="Read body from file")] = None,
        from_stdin: Annotated[bool, typer.Option("--stdin", help="Read body from stdin")] = False,
        labels: Annotated[str | None, typer.Option("-l", "--labels", help="Comma-separated labels")] = None,
        assignee: Annotated[str | None, typer.Option("-a", "--assignee", help="GitHub assignee")] = None,
        pipeline: Annotated[str | None, typer.Option("-p", "--pipeline", help="Target pipeline")] = None,
        estimate: Annotated[str | None, typer.Option("-e", "--estimate", help="Story points")] = None,
        parent: Annotated[str | None, typer.Option("--parent", help="Parent issue number")] = None,
        priority: Annotated[str | None, typer.Option("--priority", help="Priority name")] = None,
        confirm_create: Annotated[bool, typer.Option("--confirm-create", help="Bypass duplicate block")] = False,
        skip_duplicate_check: Annotated[bool, typer.Option("--skip-duplicate-check")] = False,
        related_issues: Annotated[str | None, typer.Option("--related-issues", help="Comma-separated structural-relative issue numbers")] = None,
        json_output: Annotated[bool, typer.Option("--json")] = False,
        quiet: Annotated[bool, typer.Option("-q", "--quiet", help="Emit only the new issue number")] = False,
        issue_type_flag: Annotated[str | None, typer.Option("-t", "--type", hidden=True)] = None,
    ) -> None:
        run_noun_create(
            get_state(ctx),
            type_name=type_name,
            cmd_name=cmd_name,
            title=title,
            description=description,
            body_file=body_file,
            from_stdin=from_stdin,
            labels=labels,
            assignee=assignee,
            pipeline=pipeline,
            estimate=estimate,
            parent=parent,
            priority=priority,
            confirm_create=confirm_create,
            skip_duplicate_check=skip_duplicate_check,
            related_issues=parse_related_issues(related_issues),
            json_output=json_output,
            quiet=quiet,
            issue_type_flag=issue_type_flag,
        )


def _register_list(app: typer.Typer, type_name: str, cmd_name: str) -> None:
    @app.command("list", help=f"List issues of type {type_name}")
    def list_cmd(
        ctx: typer.Context,
        extra: Annotated[list[str] | None, typer.Argument(hidden=True)] = None,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        run_noun_list(get_state(ctx), type_name=type_name, cmd_name=cmd_name, extra=extra, json_output=json_output)


def _register_show(app: typer.Typer, type_name: str) -> None:
    @app.command("show", help=f"Show a {type_name} issue and its sub-issues")
    def show_cmd(
        ctx: typer.Context,
        issue: Annotated[str, typer.Argument(help="Issue number")],
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        run_noun_show(get_state(ctx), type_name=type_name, issue=issue, json_output=json_output)


def _register_add(app: typer.Typer) -> None:
    @app.command("add", help="Attach sub-issues to a parent")
    def add_cmd(
        ctx: typer.Context,
        parent: Annotated[str, typer.Argument(help="Parent issue number")],
        children: Annotated[list[str], typer.Argument(help="Child issue numbers")],
    ) -> None:
        run_noun_add(get_state(ctx), parent=parent, children=children)


def _register_remove(app: typer.Typer) -> None:
    @app.command("remove", help="Detach sub-issues from a parent")
    def remove_cmd(
        ctx: typer.Context,
        parent: Annotated[str, typer.Argument(help="Parent issue number")],
        children: Annotated[list[str], typer.Argument(help="Child issue numbers")],
    ) -> None:
        run_noun_remove(get_state(ctx), parent=parent, children=children)


def _register_update(app: typer.Typer, type_name: str) -> None:
    @app.command("update", help="Edit title and/or body")
    def update_cmd(
        ctx: typer.Context,
        issue: Annotated[str, typer.Argument(help="Issue number")],
        title: Annotated[str | None, typer.Option("-t", "--title")] = None,
        description: Annotated[str | None, typer.Option("-d", "--description")] = None,
    ) -> None:
        run_noun_update(get_state(ctx), type_name=type_name, issue=issue, title=title, description=description)


def _register_close(app: typer.Typer, type_name: str) -> None:
    @app.command("close", help="Close the issue")
    def close_cmd(
        ctx: typer.Context,
        issue: Annotated[str, typer.Argument(help="Issue number")],
        text: Annotated[str | None, typer.Argument(help="Optional closing comment (one-liner)")] = None,
        reason: Annotated[str, typer.Option("-r", "--reason")] = "completed",
        message: Annotated[str | None, typer.Option("-m", "--message", help="Closing comment text")] = None,
        body_file: Annotated[Path | None, typer.Option("-f", "--file", help="Read closing comment from file")] = None,
        from_stdin: Annotated[bool, typer.Option("--stdin", help="Read closing comment from stdin")] = False,
        json_output: Annotated[bool, typer.Option("--json", help="JSON on stdout")] = False,
    ) -> None:
        run_noun_close(
            get_state(ctx),
            type_name=type_name,
            issue=issue,
            text=text,
            reason=reason,
            message=message,
            body_file=body_file,
            from_stdin=from_stdin,
            json_output=json_output,
        )


def _register_reopen(app: typer.Typer, type_name: str) -> None:
    @app.command("reopen", help="Reopen the issue")
    def reopen_cmd(
        ctx: typer.Context,
        issue: Annotated[str, typer.Argument(help="Issue number")],
        json_output: Annotated[bool, typer.Option("--json", help="JSON on stdout")] = False,
    ) -> None:
        run_noun_reopen(get_state(ctx), type_name=type_name, issue=issue, json_output=json_output)


def _register_delete(app: typer.Typer, type_name: str, cmd_name: str) -> None:
    @app.command("delete", help="Redirect to zh delete")
    def delete_cmd() -> None:
        run_noun_delete(type_name=type_name, cmd_name=cmd_name)


def _make_noun_app(type_name: str, cmd_name: str) -> typer.Typer:
    app = typer.Typer(
        name=cmd_name,
        help=f"Manage {type_name} issues (issue-type + sub-issue model)",
        no_args_is_help=True,
    )
    _register_create(app, type_name, cmd_name)
    _register_list(app, type_name, cmd_name)
    _register_show(app, type_name)
    _register_add(app)
    _register_remove(app)
    _register_update(app, type_name)
    _register_close(app, type_name)
    _register_reopen(app, type_name)
    _register_delete(app, type_name, cmd_name)
    return app
