"""GitHub CLI (`gh`) subprocess wrappers."""

from __future__ import annotations

import json
import shutil
import subprocess
import webbrowser
from typing import cast

from zh.api import ZhApiError
from zh.schemas import GhComment, GhIssue


def run_gh(args: list[str], *, repo: str | None = None) -> str:
    cmd = ["gh", *args]
    if repo:
        cmd.extend(["--repo", repo])
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise ZhApiError(f"gh failed: {detail or exc}") from exc
    except FileNotFoundError as exc:
        raise ZhApiError("gh CLI not found; install and authenticate gh") from exc


def gh_issue_view(owner_repo: str, number: int) -> GhIssue:
    raw = run_gh(
        ["issue", "view", str(number), "--json", "title,body,state,url,comments"],
        repo=owner_repo,
    )
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ZhApiError("Unexpected gh issue view response")
    return cast(GhIssue, data)


def gh_issue_comment(owner_repo: str, number: int, message: str) -> None:
    run_gh(["issue", "comment", str(number), "--body", message], repo=owner_repo)


def gh_issue_close(
    owner_repo: str,
    number: int,
    *,
    comment: str = "",
    reason: str = "completed",
) -> None:
    args = ["issue", "close", str(number), "--reason", reason]
    if comment:
        args.extend(["--comment", comment])
    run_gh(args, repo=owner_repo)


def gh_issue_reopen(owner_repo: str, number: int) -> None:
    run_gh(["issue", "reopen", str(number)], repo=owner_repo)


def gh_issue_delete(owner_repo: str, number: int) -> None:
    run_gh(["issue", "delete", str(number), "--yes"], repo=owner_repo)


def gh_issue_edit(owner_repo: str, number: int, *, title: str | None = None, body: str | None = None) -> None:
    if title is None and body is None:
        raise ZhApiError("Nothing to update: provide title and/or body")
    args = ["issue", "edit", str(number)]
    if title is not None:
        args.extend(["--title", title])
    if body is not None:
        args.extend(["--body", body])
    run_gh(args, repo=owner_repo)


def gh_fetch_issue_comments(owner_repo: str, number: int) -> list[GhComment]:
    raw = run_gh(
        [
            "api",
            "--paginate",
            f"repos/{owner_repo}/issues/{number}/comments",
            "--jq",
            '.[] | {id, user: .user.login, created: (.created_at // "")[0:10], body}',
        ],
        repo=None,
    )
    comments: list[GhComment] = []
    for raw_line in raw.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        row = json.loads(stripped)
        if isinstance(row, dict):
            comments.append(cast(GhComment, row))
    return comments


def gh_edit_comment(owner_repo: str, comment_id: int, body: str) -> None:
    run_gh(
        ["api", "-X", "PATCH", f"repos/{owner_repo}/issues/comments/{comment_id}", "-f", f"body={body}"],
        repo=None,
    )


def github_issue_url(owner_repo: str, number: int) -> str:
    """Canonical GitHub HTML URL for an issue."""
    return f"https://github.com/{owner_repo}/issues/{number}"


def zenhub_issue_url(workspace_id: str, owner_repo: str, number: int) -> str:
    """Canonical ZenHub app URL for an issue in a workspace."""
    return f"https://app.zenhub.com/workspaces/{workspace_id}/issues/gh/{owner_repo}/{number}"


def open_issue_url(owner_repo: str, number: int) -> str:
    url = github_issue_url(owner_repo, number)
    opened = webbrowser.open(url)
    if not opened:
        for opener in ("open", "xdg-open"):
            if shutil.which(opener):
                subprocess.run([opener, url], check=False)
                return url
    return url


def gh_current_user() -> str:
    raw = run_gh(["api", "user", "--jq", ".login"])
    login = raw.strip()
    if not login:
        raise ZhApiError("Could not get GitHub username from gh")
    return login
