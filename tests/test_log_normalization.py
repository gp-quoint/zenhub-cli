"""Tests for CLI/MCP log message normalization."""

from __future__ import annotations

from zh.log import normalize_log_message


def test_normalize_log_message_lowercases_prose() -> None:
    assert normalize_log_message("Getting board overview for acme/widgets...") == (
        "getting board overview for acme/widgets..."
    )
    assert normalize_log_message("Workspace not found") == "workspace not found"


def test_normalize_log_message_preserves_acronyms() -> None:
    assert normalize_log_message("GraphQL errors: invalid token") == "GraphQL errors: invalid token"
    assert normalize_log_message("HTTP 404 from ZenHub GraphQL") == "HTTP 404 from ZenHub GraphQL"
    assert normalize_log_message("GitHub's API does not support file uploads") == (
        "GitHub's API does not support file uploads"
    )


def test_normalize_log_message_preserves_issue_titles_after_success_colon() -> None:
    assert normalize_log_message("Created issue #1044: Set Up Libraries") == (
        "created issue #1044: Set Up Libraries"
    )
    assert normalize_log_message("Updated #42: Fix OAuth Flow") == "updated #42: Fix OAuth Flow"


def test_normalize_log_message_normalizes_non_title_colon_clauses() -> None:
    assert normalize_log_message("similarity search failed: GraphQL errors: boom") == (
        "similarity search failed: GraphQL errors: boom"
    )
    assert normalize_log_message("File not found: /tmp/missing.md") == "file not found: /tmp/missing.md"
