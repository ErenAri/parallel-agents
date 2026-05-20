from __future__ import annotations

import json
import re
from typing import Any

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
    prompt = f"Analyze this task and produce a plan:\n\n"

    if task_input.github_url:
        prompt += f"GitHub Issue: {task_input.github_url}\n"
    if task_input.repo_path:
        prompt += f"Repository path: {task_input.repo_path}\n"
    prompt += f"\nTask: {task_input.raw_input}"

    options = ClaudeCodeOptions(
        system_prompt=PLANNER_SYSTEM_PROMPT,
        model=config.planner_model,
        max_turns=20,
        permission_mode="bypassPermissions",
        cwd=task_input.repo_path,
    )

    raw_text = ""
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    raw_text += block.text

    return _parse_plan(raw_text, task_input)


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
