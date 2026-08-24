"""Tests for CLI color mode."""

from __future__ import annotations

import io

import pytest

from zh.cli.color import color_enabled, paint, parse_color_mode, set_color_mode


@pytest.fixture(autouse=True)
def _reset_color_mode() -> None:
    set_color_mode("auto")
    yield
    set_color_mode("auto")


def test_parse_color_mode_accepts_aliases() -> None:
    assert parse_color_mode("auto") == "auto"
    assert parse_color_mode("YES") == "yes"
    assert parse_color_mode("off") == "no"


def test_parse_color_mode_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Invalid --color"):
        parse_color_mode("sometimes")


def test_color_enabled_auto_follows_tty(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    set_color_mode("auto")
    assert color_enabled(io.StringIO("x")) is False
    assert color_enabled() is (not __import__("os").environ.get("NO_COLOR") and __import__("sys").stdout.isatty())


def test_color_enabled_yes_without_tty(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    set_color_mode("yes")
    assert color_enabled(io.StringIO()) is True


def test_color_enabled_no_disables_even_on_tty(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    set_color_mode("no")
    assert color_enabled() is False


def test_no_color_env_disables_even_when_yes(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    set_color_mode("yes")
    assert color_enabled() is False
    assert paint("hello", "red") == "hello"


def test_paint_wraps_when_color_enabled(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    set_color_mode("yes")
    assert paint("hello", "red") == "[red]hello[/]"
