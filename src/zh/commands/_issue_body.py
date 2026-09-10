"""Shared helpers for issue comment/edit commands."""

from __future__ import annotations

import sys
from pathlib import Path

from zh.api import ZhApiError
from zh.cli.editor import edit_text
from zh.cli.output import error, info
from zh.schemas import GhComment


def read_optional_body(
    message: str | None,
    body_file: Path | None,
    *,
    from_stdin: bool,
) -> str:
    body = message or ""
    if body_file is not None:
        if not body_file.is_file():
            error(f"File not found: {body_file}")
        body = body_file.read_text(encoding="utf-8")
    if from_stdin:
        body = sys.stdin.read()
    return body


def resolve_create_body(
    *,
    body: str | None,
    body_file: Path | None,
    from_stdin: bool,
    description: str | None = None,
) -> str:
    """Resolve issue body for create commands (-b/-d, -f, --stdin)."""
    inline = body if body is not None else description
    return read_optional_body(inline, body_file, from_stdin=from_stdin)


def comment_body_or_editor(
    message: str | None,
    body_file: Path | None,
    *,
    from_stdin: bool,
    positional: str | None = None,
) -> str | None:
    inline = message if message is not None else positional
    body = read_optional_body(inline, body_file, from_stdin=from_stdin)
    if body.strip():
        return body
    try:
        return edit_text("")
    except ZhApiError as exc:
        error(str(exc))
    return None


def apply_body_fills(body: str, fills: list[str]) -> str:
    """Replace ``{{KEY}}`` placeholders using ``KEY=value`` fill specs."""
    result = body
    for spec in fills:
        if "=" not in spec:
            error(f"invalid --fill {spec!r}; expected KEY=value (replaces {{{{KEY}}}})")
        key, _, value = spec.partition("=")
        key = key.strip()
        if not key:
            error(f"invalid --fill {spec!r}; KEY must be non-empty")
        result = result.replace("{{" + key + "}}", value)
    return result


def comment_body_for_edit(
    old_body: str,
    message: str | None,
    body_file: Path | None,
    *,
    from_stdin: bool,
    positional: str | None = None,
    fills: list[str] | None = None,
) -> str | None:
    """Resolve edited comment body: -m/-f/--stdin/positional, optional --fill, else $EDITOR."""
    fills = fills or []
    inline = message if message is not None else positional
    provided = message is not None or positional is not None or body_file is not None or from_stdin
    if provided:
        body = read_optional_body(inline, body_file, from_stdin=from_stdin)
        if not body.strip():
            error("comment body is required. use -m, -f, --stdin, or provide text as an argument.")
        return apply_body_fills(body, fills)
    if fills:
        return apply_body_fills(old_body, fills)
    try:
        return edit_text(old_body)
    except ZhApiError as exc:
        error(str(exc))
    return None


def edit_title_body_interactive(old_title: str, old_body: str) -> tuple[str, str] | None:
    seed = f"{old_title}\n\n{old_body}"
    try:
        edited = edit_text(seed)
    except ZhApiError:
        error("no tty for editor. use -t/-d/-f/--stdin for non-interactive edits.")
    if edited is None:
        info("empty or invalid buffer — cancelled")
        return None
    parts = edited.split("\n", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def annotate_comment_indices(comments: object) -> list[object]:
    """Attach 1-based ``index`` matching ``zh comment edit <N> <index>``."""
    if not isinstance(comments, list):
        return []
    out: list[object] = []
    for i, comment in enumerate(comments):
        if isinstance(comment, dict):
            out.append({**comment, "index": i + 1})
        else:
            out.append(comment)
    return out


def pick_own_comment_index(
    mine: list[tuple[int, GhComment]],
    total: int,
    index: int | None,
    me: str,
    issue_num: int,
) -> int:
    if index is not None:
        if index < 1 or index > total:
            error(
                f"comment index must be 1..{total} (got: {index}); "
                "use comments[].index from `zh issue --json` (1-based), "
                "not 0-based array offsets / jq to_entries keys"
            )
        return index
    if len(mine) == 1:
        return mine[0][0]
    error(
        f"multiple comments by @{me} on #{issue_num}; specify index (1..{total}). "
        "Run `zh issue N --json` and use comments[].index.",
    )
    return 0  # unreachable; satisfies type checker after error()


def resolve_comment_edit_target(
    comments: list[GhComment],
    *,
    index: int | None,
    me: str,
    issue_num: int,
) -> tuple[int, int, str]:
    if not comments:
        info(f"no comments on #{issue_num}")
        raise SystemExit(0)
    mine = [(i + 1, c) for i, c in enumerate(comments) if c.get("user") == me]
    if not mine:
        info(f"no editable comments on #{issue_num} (github only allows editing your own; logged in as @{me})")
        raise SystemExit(0)
    idx = pick_own_comment_index(mine, len(comments), index, me, issue_num)
    author = comments[idx - 1].get("user")
    if author != me:
        error(f"comment {idx} is by @{author} — github only allows editing your own comments (you are @{me})")
    comment_id = comments[idx - 1].get("id")
    if not isinstance(comment_id, int):
        error("invalid comment id from github")
    return idx, comment_id, str(comments[idx - 1].get("body") or "")


def resolve_issue_edit_fields(
    *,
    title: str | None,
    description: str | None,
    body_file: Path | None,
    from_stdin: bool,
    old_title: str,
    old_body: str,
) -> tuple[str | None, str | None] | None:
    body = read_optional_body(description, body_file, from_stdin=from_stdin)
    new_title: str | None = title
    new_body: str | None = None
    if description is not None or body_file is not None or from_stdin:
        new_body = body
    if title is None and description is None and body_file is None and not from_stdin:
        edited = edit_title_body_interactive(old_title, old_body)
        if edited is None:
            return None
        return edited
    return new_title, new_body
