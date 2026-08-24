"""Typer application entrypoint for the ZenHub CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer

from zh import __version__
from zh.cli.color import parse_color_mode, set_color_mode
from zh.cli.output import print_line
from zh.cli.state import CliState, apply_env_overrides
from zh.log import reconfigure_cli_logging
from zh.commands import create, discovery, issues, planning, similar, sprints, subissues

app = typer.Typer(
    name="zh",
    help="ZenHub CLI — backlog operations via GraphQL and GitHub",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)


@app.callback()
def main(
    ctx: typer.Context,
    repo: Annotated[str | None, typer.Option("-r", "--repo", help="Target GitHub repo as owner/repo")] = None,
    workspace: Annotated[str | None, typer.Option("-w", "--workspace", help="Target workspace by name")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON on stdout")] = False,
    color: Annotated[
        Literal["auto", "yes", "no"],
        typer.Option("--color", help="Color output: auto (TTY), yes, or no"),
    ] = "auto",
) -> None:
    """ZenHub backlog operations from the terminal."""
    set_color_mode(parse_color_mode(color))
    reconfigure_cli_logging()
    state = CliState(repo=repo, workspace=workspace, cwd=Path.cwd(), json_output=json_output, color=color)
    apply_env_overrides(state)
    ctx.obj = state


@app.command("version")
def version_cmd() -> None:
    """Print the installed version."""
    print_line(f"zh version {__version__}")


@app.command("help")
def help_cmd() -> None:
    """Show help."""
    print_line("ZenHub CLI — use [bold]zh --help[/bold] for the full command list.")


def _register_commands() -> None:
    discovery.register(app)
    issues.register(app)
    create.register(app)
    similar.register(app)
    sprints.register(app)
    subissues.register(app)
    planning.register(app)


_register_commands()


def run() -> None:
    app()
