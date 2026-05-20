"""Tests for GitHub tools URL parsing and issue-fetch behavior."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from parallel_agents.tools.github_tools import GitHubIssue, fetch_issue, parse_github_url


class TestParseGitHubUrl:
    def test_valid_issue_url(self):
        result = parse_github_url("https://github.com/owner/repo/issues/42")
        assert result == ("owner", "repo", 42)

    def test_valid_with_http(self):
        result = parse_github_url("http://github.com/org/project/issues/1")
        assert result == ("org", "project", 1)

    def test_invalid_url(self):
        result = parse_github_url("https://github.com/owner/repo/pulls/42")
        assert result is None

    def test_not_github(self):
        result = parse_github_url("https://gitlab.com/owner/repo/issues/42")
        assert result is None

    def test_empty_string(self):
        result = parse_github_url("")
        assert result is None

    def test_no_issue_number(self):
        result = parse_github_url("https://github.com/owner/repo/issues/")
        assert result is None


class TestFetchIssue:
    @pytest.mark.asyncio
    async def test_fetch_issue_happy_path(self):
        payload = {
            "number": 42,
            "title": "Fix auth edge case",
            "body": "Repro steps...",
            "labels": [{"name": "bug"}, {"name": "security"}],
            "state": "OPEN",
            "url": "https://github.com/owner/repo/issues/42",
            "comments": [
                {"author": {"login": "alice"}, "body": "Please prioritize this"},
                {"author": {"login": "bob"}, "body": "I can take this"},
            ],
        }

        with patch("parallel_agents.tools.github_tools._gh_available", return_value=True):
            with patch(
                "parallel_agents.tools.github_tools._run_gh",
                new=AsyncMock(return_value=(json.dumps(payload), 0)),
            ):
                issue = await fetch_issue("https://github.com/owner/repo/issues/42")

        assert isinstance(issue, GitHubIssue)
        assert issue is not None
        assert issue.number == 42
        assert issue.title == "Fix auth edge case"
        assert issue.labels == ["bug", "security"]
        assert issue.comments[0]["author"] == "alice"
        assert issue.comments[1]["body"] == "I can take this"

    @pytest.mark.asyncio
    async def test_fetch_issue_returns_none_when_gh_unavailable(self):
        with patch("parallel_agents.tools.github_tools._gh_available", return_value=False):
            issue = await fetch_issue("https://github.com/owner/repo/issues/42")
        assert issue is None
