"""Tests for GitHub tools URL parsing and issue-fetch behavior."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from parallel_agents.tools.github_tools import (
    GitHubIssue,
    create_issue,
    ensure_milestone,
    fetch_issue,
    parse_github_url,
    parse_repo_ref,
)


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


class TestParseRepoRef:
    def test_slug(self):
        assert parse_repo_ref("owner/repo") == ("owner", "repo")

    def test_url(self):
        assert parse_repo_ref("https://github.com/owner/repo") == ("owner", "repo")

    def test_invalid(self):
        assert parse_repo_ref("gitlab.com/owner/repo") is None


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


class TestMilestonesAndIssues:
    @pytest.mark.asyncio
    async def test_ensure_milestone_uses_existing(self):
        payload = [{"title": "M1", "number": 1, "state": "open", "html_url": "u"}]
        with patch("parallel_agents.tools.github_tools._gh_available", return_value=True):
            with patch(
                "parallel_agents.tools.github_tools._run_gh",
                new=AsyncMock(return_value=(json.dumps(payload), 0)),
            ):
                milestone = await ensure_milestone("owner", "repo", "M1")
        assert milestone is not None
        assert milestone.title == "M1"
        assert milestone.number == 1

    @pytest.mark.asyncio
    async def test_ensure_milestone_creates_when_missing(self):
        list_payload = []
        create_payload = {"title": "M2", "number": 2, "state": "open", "html_url": "x"}
        with patch("parallel_agents.tools.github_tools._gh_available", return_value=True):
            with patch(
                "parallel_agents.tools.github_tools._run_gh",
                new=AsyncMock(side_effect=[(json.dumps(list_payload), 0), (json.dumps(create_payload), 0)]),
            ):
                milestone = await ensure_milestone("owner", "repo", "M2")
        assert milestone is not None
        assert milestone.title == "M2"
        assert milestone.number == 2

    @pytest.mark.asyncio
    async def test_create_issue_happy_path(self):
        with patch("parallel_agents.tools.github_tools._gh_available", return_value=True):
            with patch(
                "parallel_agents.tools.github_tools._run_gh",
                new=AsyncMock(return_value=("https://github.com/owner/repo/issues/99\n", 0)),
            ):
                url = await create_issue(
                    "owner",
                    "repo",
                    "Issue title",
                    "Issue body",
                    milestone="M1",
                    labels=["planning", "ai"],
                )
        assert url == "https://github.com/owner/repo/issues/99"
