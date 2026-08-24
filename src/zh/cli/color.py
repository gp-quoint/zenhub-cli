"""Terminal color mode for CLI output (``--color``, ``NO_COLOR``) via Rich."""

from __future__ import annotations

import os
import sys
from typing import Any, Literal, TextIO

from rich.console import Console

ColorMode = Literal["auto", "yes", "no"]

_color_mode: ColorMode = "auto"
_stdout_console: Console | None = None
_stderr_console: Console | None = None


def no_color_set() -> bool:
    return "NO_COLOR" in os.environ


def parse_color_mode(value: str) -> ColorMode:
    match value.strip().casefold():
        case "auto":
            return "auto"
        case "yes" | "on" | "true" | "1":
            return "yes"
        case "no" | "off" | "false" | "0":
            return "no"
        case _:
            msg = f"Invalid --color value {value!r} (use auto, yes, or no)"
            raise ValueError(msg)


def set_color_mode(mode: ColorMode) -> None:
    global _color_mode
    _color_mode = mode
    reset_consoles()


def get_color_mode() -> ColorMode:
    return _color_mode


def reset_consoles() -> None:
    global _stdout_console, _stderr_console
    _stdout_console = None
    _stderr_console = None


def color_enabled(stream: Any = sys.stdout) -> bool:
    """Return whether styling should be emitted on ``stream``."""
    if no_color_set():
        return False
    if _color_mode == "no":
        return False
    if _color_mode == "yes":
        return True
    return hasattr(stream, "isatty") and bool(stream.isatty())


def _make_console(file: TextIO) -> Console:
    if no_color_set() or _color_mode == "no":
        return Console(file=file, no_color=True, highlight=False, soft_wrap=True)
    if _color_mode == "yes":
        return Console(file=file, force_terminal=True, highlight=False, soft_wrap=True)
    return Console(file=file, highlight=False, soft_wrap=True)


def stdout_console() -> Console:
    global _stdout_console
    if _stdout_console is None:
        _stdout_console = _make_console(sys.stdout)
    return _stdout_console


def stderr_console() -> Console:
    global _stderr_console
    if _stderr_console is None:
        _stderr_console = _make_console(sys.stderr)
    return _stderr_console


def paint(text: str, style: str, *, stream: Any = sys.stdout) -> str:
    if not color_enabled(stream):
        return text
    return f"[{style}]{text}[/]"
