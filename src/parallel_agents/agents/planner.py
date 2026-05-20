from __future__ import annotations

import json
import re

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ResultMessage,
    TextBlock,
    query,
)

from parallel_agents.config import PipelineConfig
from parallel_agents.models import TaskInput, TaskPlan

PLANNER_SYSTEM_PROMPT = """\
You are a technical project planner. Your job is to analyze a repository and a task, \
then produce a structured JSON task plan.

Analyze the repository to identify:
- Programming languages and frameworks used
- Project structure and key directories
- Architecture patterns
- Key files relevant to the task

Break the work into subtasks categorized by specialist area:
- security: OWASP checks, dependency vulnerabilities, secret scanning
- test: test coverage gaps, test generation
- perf: complexity analysis, bottleneck identification
- devops: CI/CD, Docker, deployment concerns
- arch: design patterns, SOLID principles review
- docs: documentation gaps
- code: actual implementation or refactoring
- review: code style, best practices

Output ONLY valid JSON matching this schema:
{
  "summary": "brief description of the task and approach",
  "repo_analysis": {
    "languages": ["python"],
    "frameworks": ["fastapi"],
    "structure": "description of project layout",
    "key_files": ["src/main.py"]
  },
  "subtasks": [
    {
      "id": "subtask-001",
      "description": "what this subtask should accomplish",
      "assigned_worker": "security",
      "context": {"focus_files": ["src/auth.py"]},
      "dependencies": [],
      "priority": 1
    }
  ],
  "global_context": {
    "repo_path": "/path/to/repo",
    "task_summary": "brief task description"
  }
}
"""


async def run_planner(task_input: TaskInput, config: PipelineConfig) -> TaskPlan:
    prompt = "Analyze this task and produce a plan:\n\n"

    if task_input.github_url:
        prompt += f"GitHub Issue: {task_input.github_url}\n"
    if task_input.github_issue:
        issue = task_input.github_issue
        prompt += (
            f"Issue title: {issue.title}\n"
            f"Issue state: {issue.state}\n"
            f"Issue labels: {', '.join(issue.labels) if issue.labels else '(none)'}\n"
            f"Issue body:\n{issue.body}\n"
        )
        if issue.comments:
            prompt += "Issue comments:\n"
            for comment in issue.comments[:10]:
                author = comment.get("author", "unknown")
                body = comment.get("body", "")
                prompt += f"- {author}: {body}\n"
    if task_input.repo_path:
        prompt += f"Repository path: {task_input.repo_path}\n"
    prompt += f"\nTask: {task_input.raw_input}"

    options = ClaudeCodeOptions(
        system_prompt=PLANNER_SYSTEM_PROMPT,
        model=config.planner_model,
        max_turns=20,
        permission_mode=config.permission_mode,
        cwd=task_input.repo_path,
    )

    max_attempts = max(1, config.parse_retry_attempts + 1)
    total_cost = 0.0
    token_usage: dict[str, int] = {}
    parse_retries_used = 0
    raw_text = ""
    plan = TaskPlan(summary="Failed to parse planner output")

    for attempt in range(max_attempts):
        attempt_prompt = prompt if attempt == 0 else _build_retry_prompt(prompt, raw_text)
        raw_text, attempt_cost, attempt_usage = await _run_query_once(attempt_prompt, options)
        total_cost += attempt_cost
        _merge_token_usage(token_usage, attempt_usage)

        plan = _parse_plan(raw_text, task_input)
        if not _is_parse_failure(plan):
            parse_retries_used = attempt
            break
        parse_retries_used = attempt + 1

    plan.global_context["permission_mode"] = config.permission_mode
    plan.global_context["parse_retry_attempts"] = config.parse_retry_attempts
    plan.global_context.setdefault("planner_metrics", {})
    plan.global_context["planner_metrics"].update({
        "total_cost_usd": total_cost,
        "token_usage": token_usage,
        "parse_retries_used": parse_retries_used,
    })
    return plan


async def _run_query_once(
    prompt: str,
    options: ClaudeCodeOptions,
) -> tuple[str, float, dict[str, int]]:
    raw_text = ""
    total_cost = 0.0
    token_usage: dict[str, int] = {}
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    raw_text += block.text
        elif isinstance(message, ResultMessage):
            total_cost = message.total_cost_usd or 0.0
            if message.usage:
                token_usage = message.usage
    return raw_text, total_cost, token_usage


def _merge_token_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    for key, value in usage.items():
        total[key] = total.get(key, 0) + value


def _is_parse_failure(plan: TaskPlan) -> bool:
    return plan.summary == "Failed to parse planner output" or plan.summary.startswith(
        "Planner output parse error:"
    )


def _build_retry_prompt(base_prompt: str, previous_output: str) -> str:
    return (
        f"{base_prompt}\n\n"
        "Your previous response was not valid JSON for the required schema. "
        "Return ONLY valid JSON matching the schema, with no markdown fences and no extra text.\n\n"
        "Previous response:\n"
        f"{previous_output[:12000]}"
    )


def _parse_plan(raw_output: str, task_input: TaskInput) -> TaskPlan:
    json_match = re.search(r"\{[\s\S]*\}", raw_output)
    if not json_match:
        return TaskPlan(
            summary="Failed to parse planner output",
            repo_analysis={},
            subtasks=[],
            global_context={"repo_path": task_input.repo_path, "raw_planner_output": raw_output},
        )

    try:
        data = json.loads(json_match.group())
        if task_input.repo_path:
            data.setdefault("global_context", {})["repo_path"] = task_input.repo_path
        return TaskPlan(**data)
    except (json.JSONDecodeError, Exception) as e:
        return TaskPlan(
            summary=f"Planner output parse error: {e}",
            repo_analysis={},
            subtasks=[],
            global_context={"repo_path": task_input.repo_path, "raw_planner_output": raw_output},
        )
