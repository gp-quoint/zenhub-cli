"""Similarity search commands."""

from __future__ import annotations

from typing import Annotated

import typer

from zh.cli.context import get_state
from zh.cli.output import emit_json, error, info, print_line
from zh.similarity import find_similar, reindex


def register(app: typer.Typer) -> None:
    app.command("similar", help="Find issues semantically similar to a query")(similar_cmd)
    app.command("reindex", help="Refresh the similarity-search cache")(reindex_cmd)


def similar_cmd(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Natural-language search query")],
    top_k: Annotated[int, typer.Option("--top-k", "-k", help="Max results")] = 5,
    threshold: Annotated[float, typer.Option("--threshold", "-t", help="Cosine threshold")] = 0.35,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Find issues semantically similar to a query."""
    state = get_state(ctx)
    repo = state.context().owner_repo
    try:
        matches = find_similar(query, repo, top_k=top_k, threshold=threshold, min_results=top_k)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        error(f"similarity search failed: {exc}")
    payload = {
        "ok": True,
        "repo": repo,
        "query": query,
        "threshold": threshold,
        "matches": [m.to_dict() for m in matches],
        "any_above_threshold": any(m.meets_threshold for m in matches),
    }
    if json_output or state.json_output:
        emit_json(payload)
        return
    info(f"Similar issues in {repo} for: {query!r}")
    for m in matches:
        flag = "✓" if m.meets_threshold else "·"
        print_line(f"  {flag} #{m.number} ({m.similarity:.3f}) {m.title}")


def reindex_cmd(
    ctx: typer.Context,
    full: Annotated[bool, typer.Option("--full", help="Full rebuild instead of delta sync")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Refresh the similarity-search cache."""
    state = get_state(ctx)
    repo = state.context().owner_repo
    try:
        result = reindex(repo, full=full)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        error(f"reindex failed: {exc}")
    payload = {"ok": True, "repo": repo, **result}
    if json_output or state.json_output:
        emit_json(payload)
        return
    info(f"Reindexed {repo}: {result}")
