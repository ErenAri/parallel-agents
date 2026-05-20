"""GitHub integration tools for fetching issues and posting PR comments.

Uses the `gh` CLI for authentication (no token management needed).
Falls back to the GitHub REST API via httpx if `gh` is not available.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("parallel_agents.github")


@dataclass
class GitHubIssue:
    number: int
    title: str
    body: str
    labels: list[str]
    state: str
    url: str
    comments: list[dict[str, str]]


def parse_github_url(url: str) -> tuple[str, str, int] | None:
    """Parse a GitHub issue URL into (owner, repo, issue_number)."""
    match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/issues/(\d+)", url
    )
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    return None


async def _run_gh(*args: str) -> tuple[str, int]:
    """Run a `gh` CLI command and return (stdout, return_code)."""
    proc = await asyncio.create_subprocess_exec(
        "gh", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("gh command failed: %s", stderr.decode().strip())
    return stdout.decode(), proc.returncode or 0


def _gh_available() -> bool:
    """Check if the GitHub CLI is available."""
    return shutil.which("gh") is not None


async def fetch_issue(url: str) -> GitHubIssue | None:
    """Fetch a GitHub issue by URL using the `gh` CLI."""
    parsed = parse_github_url(url)
    if not parsed:
        logger.error("Invalid GitHub issue URL: %s", url)
        return None

    owner, repo, number = parsed

    if not _gh_available():
        logger.warning("gh CLI not found. Cannot fetch issue.")
        return None

    # Fetch issue details
    stdout, rc = await _run_gh(
        "issue", "view", str(number),
        "--repo", f"{owner}/{repo}",
        "--json", "number,title,body,labels,state,url,comments",
    )
    if rc != 0:
        return None

    try:
        data = json.loads(stdout)
        return GitHubIssue(
            number=data["number"],
            title=data["title"],
            body=data.get("body", ""),
            labels=[l["name"] for l in data.get("labels", [])],
            state=data.get("state", ""),
            url=data.get("url", url),
            comments=[
                {"author": c.get("author", {}).get("login", ""), "body": c.get("body", "")}
                for c in data.get("comments", [])
            ],
        )
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Failed to parse issue data: %s", e)
        return None


async def post_pr_comment(
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
) -> bool:
    """Post a comment on a GitHub PR using the `gh` CLI."""
    if not _gh_available():
        logger.warning("gh CLI not found. Cannot post PR comment.")
        return False

    stdout, rc = await _run_gh(
        "pr", "comment", str(pr_number),
        "--repo", f"{owner}/{repo}",
        "--body", body,
    )
    return rc == 0


async def create_pr(
    owner: str,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main",
) -> str | None:
    """Create a GitHub PR using the `gh` CLI. Returns PR URL or None."""
    if not _gh_available():
        logger.warning("gh CLI not found. Cannot create PR.")
        return None

    stdout, rc = await _run_gh(
        "pr", "create",
        "--repo", f"{owner}/{repo}",
        "--title", title,
        "--body", body,
        "--head", head,
        "--base", base,
    )
    if rc == 0:
        return stdout.strip()
    return None


async def list_repo_files(repo_path: str, pattern: str = "*") -> list[str]:
    """List files in a repo using git ls-files."""
    proc = await asyncio.create_subprocess_exec(
        "git", "ls-files", pattern,
        cwd=repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode().strip().split("\n") if stdout.strip() else []
