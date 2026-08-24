"""Optional duplicate-check preflight for create commands."""

from __future__ import annotations

from zh.cli.output import info
from zh.issue_ops import parse_issue_number
from zh.schemas import DuplicateCheckResult
from zh.similarity import check_duplicate


def parse_related_issues(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    nums: list[int] = []
    for piece in raw.split(","):
        token = piece.strip()
        if not token:
            continue
        nums.append(parse_issue_number(token))
    return nums or None


def optional_duplicate_check(
    *,
    title: str,
    body: str,
    owner_repo: str,
    parent: int | None,
    related_issues: list[int] | None = None,
    skip: bool,
) -> DuplicateCheckResult | None:
    if skip:
        return None
    try:
        return check_duplicate(
            title,
            body,
            owner_repo,
            parent=parent,
            related_issues=related_issues,
        )
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        info(f"duplicate check skipped: {exc}")
        return None
