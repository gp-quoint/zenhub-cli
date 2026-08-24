"""Human-readable and JSON terminal output helpers."""

from __future__ import annotations

import json
import sys
from typing import NoReturn

from zh.cli.color import color_enabled, stderr_console, stdout_console
from zh.log import configure_cli_logging, normalize_log_message
from zh.schemas import CreateIssueResult

configure_cli_logging()


def error(message: str, *, exit_code: int = 1) -> NoReturn:
    message = normalize_log_message(message)
    console = stderr_console()
    if color_enabled(sys.stderr):
        console.print(f"[red bold]error:[/] {message}")
    else:
        console.print(f"error: {message}")
    raise SystemExit(exit_code)


def warn(message: str) -> None:
    message = normalize_log_message(message)
    console = stderr_console()
    if color_enabled(sys.stderr):
        console.print(f"[yellow]warning:[/] {message}")
    else:
        console.print(f"warning: {message}")


def info(message: str) -> None:
    message = normalize_log_message(message)
    console = stderr_console()
    if color_enabled(sys.stderr):
        console.print(f"[blue]info:[/] {message}")
    else:
        console.print(f"info: {message}")


def success(message: str) -> None:
    message = normalize_log_message(message)
    console = stderr_console()
    if color_enabled(sys.stderr):
        console.print(f"[green]✓[/] {message}")
    else:
        console.print(f"✓ {message}")


def emit_create_links(created: CreateIssueResult) -> None:
    """Print ZenHub and GitHub URLs after a successful create (stdout)."""
    zenhub = created.get("zenhub_url")
    github = created.get("github_url") or created.get("url")
    if zenhub:
        print_line(f"  ZenHub: {zenhub}")
    if github:
        print_line(f"  GitHub: {github}")


def emit_json(data: object) -> None:
    json.dump(data, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    sys.stdout.flush()


def print_line(message: str) -> None:
    stdout_console().print(message, markup=True)
