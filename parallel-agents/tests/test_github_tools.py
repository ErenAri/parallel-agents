"""Unit tests for GitHub tools — URL parsing (no network calls)."""

from __future__ import annotations

from parallel_agents.tools.github_tools import parse_github_url


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
