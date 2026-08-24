"""Fixed-width table formatters for CLI listings."""

from __future__ import annotations

from zh.cli.color import paint
from zh.schemas import PipelineIssueRow


def _common_owner_prefix(repos: list[str]) -> str | None:
    if not repos:
        return None
    owners: set[str] = set()
    for repo in repos:
        owner, sep, _name = repo.partition("/")
        if not sep:
            return None
        owners.add(owner)
    if len(owners) != 1:
        return None
    return f"{owners.pop()}/"


def _display_repo(repo: str, owner_prefix: str | None) -> str:
    if owner_prefix and repo.startswith(owner_prefix):
        return repo[len(owner_prefix) :]
    return repo


def format_pipeline_issues_table(issues: list[PipelineIssueRow]) -> list[str]:
    """Render pipeline issue rows as aligned single-line records."""
    if not issues:
        return []

    repos = [str(issue.get("repo") or "") for issue in issues]
    owner_prefix = _common_owner_prefix(repos)

    rows = [
        (
            f"#{issue.get('number')}",
            _display_repo(str(issue.get("repo") or ""), owner_prefix),
            str(issue.get("estimate")) if issue.get("estimate") is not None else "-",
            str(issue.get("assignee") or "-"),
            str(issue.get("title") or ""),
        )
        for issue in issues
    ]

    num_w = max(len(num) for num, *_rest in rows)
    repo_w = max(len(repo) for _num, repo, *_rest in rows)
    est_w = max(len(est) for _num, _repo, est, *_rest in rows)
    asg_w = max(len(asg) for _num, _repo, _est, asg, *_rest in rows)

    lines: list[str] = []
    for num, repo, est, asg, title in rows:
        num_s = paint(f"{num:<{num_w}}", "cyan bold")
        repo_s = paint(f"{repo:<{repo_w}}", "blue")
        est_s = paint(f"{est:>{est_w}}", "dim")
        asg_s = paint(f"{asg:<{asg_w}}", "yellow")
        title_s = paint(title, "white") if title else title
        lines.append(f"  {num_s} │ {repo_s} │ {est_s} │ {asg_s} │ {title_s}")
    return lines


def format_mine_issues_list(
    issues: list[PipelineIssueRow],
    *,
    include_urls: bool = True,
    shorten_repo: bool = False,
) -> list[str]:
    """Render mine rows: aligned header line, title, optional URL."""
    if not issues:
        return []

    repos = [str(issue.get("repo") or "") for issue in issues]
    owner_prefix = _common_owner_prefix(repos) if shorten_repo else None

    header_rows = [
        (
            f"#{issue.get('number')}",
            _display_repo(str(issue.get("repo") or ""), owner_prefix),
            str(issue.get("pipeline") or "-"),
        )
        for issue in issues
    ]

    num_w = max(len(num) for num, *_rest in header_rows)
    repo_w = max(len(repo) for _num, repo, *_rest in header_rows)
    pipe_w = max(len(pipe) for _num, _repo, pipe, *_rest in header_rows)

    lines: list[str] = []
    for issue, (num, repo, pipe) in zip(issues, header_rows, strict=True):
        num_s = paint(f"{num:<{num_w}}", "cyan bold")
        repo_s = paint(f"{repo:<{repo_w}}", "blue")
        pipe_s = paint(f"{pipe:<{pipe_w}}", "magenta")
        lines.append(f"  {num_s} │ {repo_s} │ {pipe_s}")
        title = str(issue.get("title") or "")
        if title:
            lines.append(f"    {paint(title, 'white')}")
        if include_urls:
            url = issue.get("url")
            if url:
                lines.append(f"    {paint('→', 'dim')} {paint(str(url), 'dim underline')}")
    return lines


def format_board_overview_lines(
    *,
    workspace: str | None,
    total: int,
    label: str,
    pipelines: dict[str, int],
    bar_max: int,
) -> list[str]:
    header = f"Board: {workspace} ({total} {label} issues)"
    lines = [paint(f"\n{header}\n", "bold")]
    for name, count in pipelines.items():
        bar = "█" * min(count, bar_max)
        suffix = "…" if count > bar_max else ""
        name_s = paint(f"{name:<25}", "magenta")
        count_s = paint(f"{count:3d}", "cyan bold")
        bar_s = paint(f"{bar}{suffix}", "green")
        lines.append(f"  {name_s} {count_s} {bar_s}")
    lines.append("")
    return lines


def sprint_heading(name: str | None) -> str:
    """Format a sprint detail header without duplicating ZenHub's ``Sprint:`` prefix."""
    label = (name or "?").strip()
    prefix, sep, rest = label.partition(":")
    if sep and prefix.casefold() == "sprint":
        label = rest.lstrip()
    return paint(f"Sprint: {label}", "bold")
