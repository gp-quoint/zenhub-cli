"""Shared close/reopen body resolution and JSON emit helpers."""

from __future__ import annotations

from pathlib import Path

from zh.api import RepoContext, ZhApiError
from zh.cli.output import emit_json, error, success
from zh.commands._issue_body import read_optional_body
from zh.gh_ops import gh_issue_close, gh_issue_reopen, gh_issue_view
from zh.issue_ops import issue_zenhub_summary


def resolve_closing_body(
    message: str | None,
    positional: str | None,
    body_file: Path | None,
    *,
    from_stdin: bool,
) -> str:
    """Resolve optional closing comment: -m wins over positional; -f/--stdin override."""
    return read_optional_body(
        message if message is not None else positional,
        body_file,
        from_stdin=from_stdin,
    )


def optional_gh_issue_title(owner_repo: str, number: int) -> str | None:
    try:
        issue_view = gh_issue_view(owner_repo, number)
        raw_title = issue_view.get("title")
        return str(raw_title) if raw_title is not None else None
    except ZhApiError:
        return None


def optional_workspace_pipeline(ctx: RepoContext, number: int) -> str | None:
    try:
        summary = issue_zenhub_summary(ctx, number)
        pipeline_name = summary.get("pipeline")
        return str(pipeline_name) if pipeline_name else None
    except ZhApiError:
        return None


def close_issue_with_output(
    ctx: RepoContext,
    number: int,
    *,
    body: str,
    reason: str,
    should_emit_json: bool,
) -> None:
    title: str | None = None
    pipeline: str | None = None
    if should_emit_json:
        title = optional_gh_issue_title(ctx.owner_repo, number)
        pipeline = optional_workspace_pipeline(ctx, number)
    try:
        gh_issue_close(ctx.owner_repo, number, comment=body, reason=reason)
    except ZhApiError as exc:
        error(str(exc))
    if should_emit_json:
        payload: dict[str, object] = {
            "ok": True,
            "number": number,
            "title": title,
            "state": "CLOSED",
            "reason": reason,
            # True when non-empty closing text was supplied (not a gh post ack).
            "comment_added": bool(body.strip()),
        }
        if pipeline is not None:
            payload["pipeline"] = pipeline
        emit_json(payload)
        return
    success(f"Closed #{number}")


def reopen_issue_with_output(
    ctx: RepoContext,
    number: int,
    *,
    should_emit_json: bool,
) -> None:
    title: str | None = None
    if should_emit_json:
        title = optional_gh_issue_title(ctx.owner_repo, number)
    try:
        gh_issue_reopen(ctx.owner_repo, number)
    except ZhApiError as exc:
        error(str(exc))
    if should_emit_json:
        emit_json(
            {
                "ok": True,
                "number": number,
                "title": title,
                "state": "OPEN",
            }
        )
        return
    success(f"Reopened #{number}")
