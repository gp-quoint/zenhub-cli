"""Click/Typer group that defaults to a named subcommand."""

from __future__ import annotations

import click
from typer.core import TyperGroup


class DefaultCommandGroup(TyperGroup):
    """Insert ``default_command`` when the first token is not a known subcommand.

    Enables patterns like:
    - ``zh comment 42 -f body.md`` (default ``add``) while keeping ``zh comment edit 42``
    - ``zh sprint current`` (default ``show``) while keeping ``zh sprint add current 42``

    Without this, Click treats a non-subcommand first token as an error (or, when a
    callback also takes an optional Argument, steals the real subcommand name).
    """

    default_command: str = "add"

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        args = list(args)
        if args:
            head = args[0]
            help_names = set(self.get_help_option_names(ctx))
            if head not in self.commands and head not in help_names:
                args.insert(0, self.default_command)
        return super().parse_args(ctx, args)
