"""GitHub issue-plan execution.

Extracted from main.py so non-CLI callers (engine service, desktop app) can
import the executor without dragging click and the rest of the CLI module
into their import graph.
"""

from __future__ import annotations

from typing import Any

from parallel_agents.tools.github_tools import create_issue, ensure_milestone


def issue_field(issue: Any, key: str, default: Any) -> Any:
    if isinstance(issue, dict):
        return issue.get(key, default)
    return getattr(issue, key, default)


async def execute_company_issue_plan(
    *,
    owner: str,
    repo: str,
    issue_plan: list[Any],
    create_milestones: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Apply an issue plan to a GitHub repository (dry-run or live)."""
    milestone_results: list[dict[str, Any]] = []
    issue_results: list[dict[str, Any]] = []
    milestone_seen: set[str] = set()
    normalized_plan: list[dict[str, Any]] = []

    for planned_issue in issue_plan:
        source_item_id = str(issue_field(planned_issue, "source_item_id", ""))
        title = str(issue_field(planned_issue, "title", ""))
        body = str(issue_field(planned_issue, "body", ""))
        milestone_name = str(issue_field(planned_issue, "milestone", ""))
        raw_labels = issue_field(planned_issue, "labels", [])
        labels = list(raw_labels) if isinstance(raw_labels, list) else []

        normalized_plan.append({
            "source_item_id": source_item_id,
            "title": title,
            "body": body,
            "milestone": milestone_name,
            "labels": labels,
        })

        if milestone_name and milestone_name not in milestone_seen:
            milestone_seen.add(milestone_name)
            milestone_entry = {
                "title": milestone_name,
                "ensured": False,
                "created": False,
                "status": "skipped",
            }
            if create_milestones:
                if dry_run:
                    milestone_entry["status"] = "planned"
                else:
                    ensured = await ensure_milestone(owner, repo, milestone_name)
                    milestone_entry["ensured"] = ensured is not None
                    milestone_entry["created"] = ensured is not None
                    milestone_entry["status"] = "ensured" if ensured else "failed"
            milestone_results.append(milestone_entry)

        issue_entry = {
            "source_item_id": source_item_id,
            "title": title,
            "milestone": milestone_name,
            "labels": labels,
            "created": False,
            "url": None,
            "status": "planned" if dry_run else "pending",
        }
        if not dry_run:
            issue_url = await create_issue(
                owner,
                repo,
                title,
                body,
                milestone=milestone_name or None,
                labels=labels,
            )
            issue_entry["created"] = issue_url is not None
            issue_entry["url"] = issue_url
            issue_entry["status"] = "created" if issue_url else "failed"
        issue_results.append(issue_entry)

    return {
        "repo": f"{owner}/{repo}",
        "dry_run": dry_run,
        "milestones": milestone_results,
        "issues": issue_results,
        "issue_plan": normalized_plan,
        "create_milestones": create_milestones,
    }
