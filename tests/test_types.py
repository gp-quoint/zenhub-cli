"""Tests for shared type helpers."""

from __future__ import annotations

import pytest

from zh.types import reorder_position, sprint_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("top", 0),
        ("first", 0),
        ("0", 0),
        ("bottom", 4),
        ("last", 4),
        ("2", 2),
    ],
)
def test_reorder_position(raw: str, expected: int) -> None:
    assert reorder_position(raw, total_count=5) == expected


def test_reorder_position_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="Invalid position"):
        reorder_position("middle", total_count=5)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (None, "current"),
        ("current", "current"),
        ("active", "current"),
        ("Sprint 42", "Sprint 42"),
    ],
)
def test_sprint_key(name: str | None, expected: str) -> None:
    assert sprint_key(name) == expected
