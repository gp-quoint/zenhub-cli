"""CLI layer for the ZenHub command-line tool."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from zh.api import RepoContext, resolve_context


@dataclass(frozen=True, slots=True)
class CliState:
    """Global options peeled off before subcommands."""

    repo: str | None = None
    workspace: str | None = None
    cwd: Path | None = None
    json_output: bool = False
    color: str = "auto"
    _cached_context: RepoContext | None = field(default=None, compare=False, hash=False, repr=False)

    def context(self) -> RepoContext:
        cached = self._cached_context
        if cached is not None:
            return cached
        ctx = resolve_context(
            cwd=self.cwd,
            owner_repo=self.repo,
            workspace_name=self.workspace,
        )
        object.__setattr__(self, "_cached_context", ctx)
        return ctx


def apply_env_overrides(state: CliState) -> None:
    """Mirror bash `-r` / `-w` by exporting override env vars for child tools."""
    if state.repo:
        os.environ["ZH_REPO_OVERRIDE"] = state.repo
    if state.workspace:
        os.environ["ZH_WORKSPACE_NAME"] = state.workspace
