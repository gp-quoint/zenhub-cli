"""Shared Typer context helpers."""

from __future__ import annotations

import typer

from zh.cli.output import error
from zh.cli.state import CliState


def get_state(ctx: typer.Context) -> CliState:
    state = ctx.obj
    if not isinstance(state, CliState):
        error("Internal error: CLI state missing")
    return state
