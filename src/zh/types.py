"""Shared type aliases and small domain helpers."""

from __future__ import annotations

type JsonDict = dict[str, object]
type GraphQLVariables = dict[str, object]


def sprint_key(name: str | None) -> str:
    """Normalize sprint CLI aliases to a lookup key."""
    match name:
        case None | "current" | "active":
            return "current"
        case other:
            return other


def reorder_position(raw: str, *, total_count: int) -> int:
    """Parse a pipeline reorder target (number, top, or bottom)."""
    match raw.lower():
        case "top" | "first" | "0":
            return 0
        case "bottom" | "last":
            return max(total_count - 1, 0)
        case digits if digits.isdecimal():
            return int(digits)
        case _:
            msg = f"Invalid position: {raw!r} (use a number, 'top', or 'bottom')"
            raise ValueError(msg)
