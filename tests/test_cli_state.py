"""Tests for CLI global state."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import zh.api
from zh.cli.state import CliState


def test_cli_state_caches_repo_context_for_command_lifetime() -> None:
    calls = 0

    def _resolve_context(**_kwargs: object) -> zh.api.RepoContext:
        nonlocal calls
        calls += 1
        return zh.api.RepoContext(
            owner_repo="acme/widgets",
            repo_id="repo-gid",
            workspace_id="workspace-gid",
            token="token",
        )

    state = CliState(cwd=Path("/tmp/project"))
    with patch("zh.cli.state.resolve_context", side_effect=_resolve_context):
        first = state.context()
        second = state.context()

    assert calls == 1
    assert first is second
