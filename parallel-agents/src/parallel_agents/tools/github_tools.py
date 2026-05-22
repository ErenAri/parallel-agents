"""GitHub integration tools for fetching issues and posting PR comments.

Uses the `gh` CLI for authentication (no token management needed).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from dataclasses import dataclass

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


@dataclass
class GitHubMilestone:
    title: str
    number: int | None = None
    state: str = "open"
    url: str = ""


@dataclass
class GitHubPullRequest:
    number: int
    title: str
    state: str
    url: str
    merged_at: str | None = None
    review_decision: str | None = None
    changes_requested_count: int = 0
    approved_count: int = 0
    changed_files: int = 0
    additions: int = 0
    deletions: int = 0


def parse_github_url(url: str) -> tuple[str, str, int] | None:
    """Parse a GitHub issue URL into (owner, repo, issue_number)."""
    match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/issues/(\d+)", url
    )
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    return None


def parse_pr_url(url: str) -> tuple[str, str, int] | None:
    """Parse a GitHub PR URL into (owner, repo, pull_number)."""
    match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/pull(?:s)?/(\d+)", url
    )
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    return None


def parse_repo_ref(ref: str) -> tuple[str, str] | None:
    """Parse owner/repo or GitHub URL into (owner, repo)."""
    normalized = ref.strip()
    if not normalized:
        return None

    slug_match = re.fullmatch(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", normalized)
    if slug_match:
        return slug_match.group(1), slug_match.group(2)

    url_match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/?", normalized)
    if url_match:
        return url_match.group(1), url_match.group(2)
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
            labels=[label["name"] for label in data.get("labels", [])],
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


async def fetch_pull_request(url: str) -> GitHubPullRequest | None:
    """Fetch a GitHub PR by URL using the `gh` CLI."""
    parsed = parse_pr_url(url)
    if not parsed:
        logger.error("Invalid GitHub PR URL: %s", url)
        return None

    owner, repo, number = parsed
    if not _gh_available():
        logger.warning("gh CLI not found. Cannot fetch PR.")
        return None

    stdout, rc = await _run_gh(
        "pr",
        "view",
        str(number),
        "--repo",
        f"{owner}/{repo}",
        "--json",
        "number,title,state,url,mergedAt,reviewDecision,reviews,changedFiles,additions,deletions",
    )
    if rc != 0:
        return None

    try:
        data = json.loads(stdout)
        reviews = data.get("reviews", [])
        states = [str(review.get("state", "")).upper() for review in reviews]
        changes_requested_count = sum(1 for state in states if state == "CHANGES_REQUESTED")
        approved_count = sum(1 for state in states if state == "APPROVED")
        return GitHubPullRequest(
            number=int(data["number"]),
            title=str(data.get("title", "")),
            state=str(data.get("state", "")),
            url=str(data.get("url", url)),
            merged_at=data.get("mergedAt"),
            review_decision=(
                str(data["reviewDecision"]) if data.get("reviewDecision") is not None else None
            ),
            changes_requested_count=changes_requested_count,
            approved_count=approved_count,
            changed_files=int(data.get("changedFiles", 0) or 0),
            additions=int(data.get("additions", 0) or 0),
            deletions=int(data.get("deletions", 0) or 0),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.error("Failed to parse PR data: %s", exc)
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
    draft: bool = False,
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
        *(["--draft"] if draft else []),
    )
    if rc == 0:
        return stdout.strip()
    return None


async def list_milestones(owner: str, repo: str, state: str = "all") -> list[GitHubMilestone]:
    """List repository milestones via gh api."""
    if not _gh_available():
        logger.warning("gh CLI not found. Cannot list milestones.")
        return []

    stdout, rc = await _run_gh(
        "api",
        f"repos/{owner}/{repo}/milestones",
        "-f",
        f"state={state}",
    )
    if rc != 0:
        return []

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    milestones: list[GitHubMilestone] = []
    for item in payload:
        milestones.append(
            GitHubMilestone(
                title=item.get("title", ""),
                number=item.get("number"),
                state=item.get("state", "open"),
                url=item.get("html_url", ""),
            )
        )
    return milestones


async def create_milestone(
    owner: str,
    repo: str,
    title: str,
    description: str = "",
) -> GitHubMilestone | None:
    """Create a repository milestone via gh api."""
    if not _gh_available():
        logger.warning("gh CLI not found. Cannot create milestone.")
        return None

    args = [
        "api",
        "--method",
        "POST",
        f"repos/{owner}/{repo}/milestones",
        "-f",
        f"title={title}",
    ]
    if description:
        args.extend(["-f", f"description={description}"])

    stdout, rc = await _run_gh(*args)
    if rc != 0:
        return None

    try:
        payload = json.loads(stdout)
        return GitHubMilestone(
            title=payload.get("title", title),
            number=payload.get("number"),
            state=payload.get("state", "open"),
            url=payload.get("html_url", ""),
        )
    except json.JSONDecodeError:
        return GitHubMilestone(title=title)


async def ensure_milestone(
    owner: str,
    repo: str,
    title: str,
    description: str = "",
) -> GitHubMilestone | None:
    """Ensure a milestone exists by title, creating one if needed."""
    if not title.strip():
        return None

    existing = await list_milestones(owner, repo, state="all")
    for milestone in existing:
        if milestone.title.strip().lower() == title.strip().lower():
            return milestone
    return await create_milestone(owner, repo, title=title, description=description)


async def create_issue(
    owner: str,
    repo: str,
    title: str,
    body: str,
    *,
    milestone: str | None = None,
    labels: list[str] | None = None,
) -> str | None:
    """Create a GitHub issue via gh CLI and return created URL when available."""
    if not _gh_available():
        logger.warning("gh CLI not found. Cannot create issue.")
        return None

    args: list[str] = [
        "issue", "create",
        "--repo", f"{owner}/{repo}",
        "--title", title,
        "--body", body,
    ]
    if milestone:
        args.extend(["--milestone", milestone])
    if labels:
        args.extend(["--label", ",".join(labels)])

    stdout, rc = await _run_gh(*args)
    if rc != 0:
        return None
    return stdout.strip() or None


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
