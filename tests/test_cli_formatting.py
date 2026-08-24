"""Tests for CLI table formatters."""

from __future__ import annotations

from zh.cli.formatting import format_mine_issues_list, format_pipeline_issues_table, sprint_heading


def test_format_pipeline_issues_table_aligns_columns() -> None:
    issues = [
        {
            "number": 4,
            "repo": "QuoIntelligence/aws-demeter-resultbroker",
            "estimate": None,
            "assignee": "giuseppevavalaqi",
            "title": "Finalize and deploy the resultbroker infrastructure",
        },
        {
            "number": 1044,
            "repo": "QuoIntelligence/quollection",
            "estimate": 8.0,
            "assignee": "gp-quoint",
            "title": "Set up data-team-python-libs",
        },
    ]

    lines = format_pipeline_issues_table(issues)

    assert len(lines) == 2
    assert lines[0].index("│") == lines[1].index("│")
    repo_col_start = lines[0].index("│") + 2
    repo_col_end = lines[0].index("│", repo_col_start)
    assert lines[0][repo_col_start:repo_col_end].strip() == "aws-demeter-resultbroker"
    assert lines[1][repo_col_start:repo_col_end].strip() == "quollection"


def test_sprint_heading_strips_redundant_prefix() -> None:
    assert sprint_heading("Sprint: Apr 21 - May 5, 2026") == "Sprint: Apr 21 - May 5, 2026"
    assert sprint_heading("Sprint 7") == "Sprint: Sprint 7"


def test_format_mine_issues_list_aligns_header_and_keeps_title_block() -> None:
    issues = [
        {
            "number": 4,
            "repo": "QuoIntelligence/quollection",
            "pipeline": "New Issues",
            "title": "Short task",
            "url": "https://app.zenhub.com/workspaces/w/issues/4",
        },
        {
            "number": 1044,
            "repo": "QuoIntelligence/aws-demeter-resultbroker",
            "pipeline": "In Progress",
            "title": "Finalize and deploy the resultbroker infrastructure",
            "url": "https://app.zenhub.com/workspaces/w/issues/1044",
        },
    ]

    lines = format_mine_issues_list(issues)

    assert lines[0].index("│") == lines[3].index("│")
    assert "QuoIntelligence/quollection" in lines[0]
    assert lines[1] == "    Short task"
    assert lines[2].startswith("    → https://")
    assert lines[4] == "    Finalize and deploy the resultbroker infrastructure"


def test_format_mine_issues_list_hides_urls_when_requested() -> None:
    issues = [
        {
            "number": 1,
            "repo": "acme/widgets",
            "pipeline": "TO DO",
            "title": "One",
            "url": "https://example.com/1",
        }
    ]

    lines = format_mine_issues_list(issues, include_urls=False)

    assert lines == ["  #1 │ acme/widgets │ TO DO", "    One"]


def test_format_pipeline_issues_table_keeps_owner_when_mixed() -> None:
    issues = [
        {"number": 1, "repo": "acme/widgets", "estimate": 2, "assignee": "alice", "title": "One"},
        {"number": 2, "repo": "other/things", "estimate": 3, "assignee": "bob", "title": "Two"},
    ]

    lines = format_pipeline_issues_table(issues)

    assert "acme/widgets" in lines[0]
    assert "other/things" in lines[1]
