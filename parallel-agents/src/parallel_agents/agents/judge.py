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
from parallel_agents.models import (
    Finding,
    FinalOutput,
    TaskPlan,
    WorkerResult,
)

JUDGE_SYSTEM_PROMPT = """\
You are the Judge/Arbiter agent. You receive structured findings and recommendations \
from multiple specialist agents who analyzed a codebase in parallel.

Your responsibilities:
1. MERGE: Combine all worker findings into a unified report
2. RESOLVE: When recommendations conflict (e.g., Code Agent suggests X but Security \
Agent flags it as insecure), decide the right approach and document your reasoning
3. PRIORITIZE: Order recommendations by importance and impact
4. PATCH: Produce the FINAL unified diff/patch that implements all approved changes
5. SUMMARIZE: Write a PR summary suitable for a pull request description
6. RISK: Compile a risk report highlighting critical and high severity findings

You are the ONLY agent that produces diffs/patches. Workers provide recommendations; \
you synthesize them into concrete changes.

Output a JSON object with this structure:
{
  "summary": "what was analyzed and key findings",
  "risk_report": [<Finding objects for critical/high items>],
  "patch": "unified diff string (or null if no code changes)",
  "pr_summary": "markdown PR description",
  "conflicts_resolved": [
    {"between": ["worker1", "worker2"], "issue": "description", "resolution": "what you decided"}
  ]
}

Be thorough but practical. If workers disagree, favor security over convenience.
"""


async def run_judge(
    plan: TaskPlan,
    worker_results: dict[str, WorkerResult],
    config: PipelineConfig,
) -> FinalOutput:
    prompt = _build_judge_prompt(plan, worker_results)

    options = ClaudeCodeOptions(
        system_prompt=JUDGE_SYSTEM_PROMPT,
        model=config.judge_model,
        max_turns=30,
        permission_mode="bypassPermissions",
        cwd=plan.global_context.get("repo_path"),
    )

    raw_text = ""
    total_cost = 0.0
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    raw_text += block.text
        elif isinstance(message, ResultMessage):
            total_cost = message.total_cost_usd or 0.0

    return _parse_judge_output(raw_text, worker_results, total_cost)


def _build_judge_prompt(
    plan: TaskPlan,
    worker_results: dict[str, WorkerResult],
) -> str:
    sections = [
        f"## Task Summary\n{plan.summary}\n",
        f"## Repository Analysis\n{json.dumps(plan.repo_analysis, indent=2)}\n",
    ]

    for name, result in worker_results.items():
        findings_json = json.dumps([f.model_dump() for f in result.findings], indent=2, default=str)
        recs_json = json.dumps([r.model_dump() for r in result.recommendations], indent=2, default=str)
        sections.append(
            f"## Worker: {name} (status: {result.status})\n"
            f"### Findings\n{findings_json}\n"
            f"### Recommendations\n{recs_json}\n"
        )

    sections.append(
        "## Instructions\n"
        "Merge all findings and recommendations above. Resolve any conflicts. "
        "Produce the final JSON output with summary, risk_report, patch, "
        "pr_summary, and conflicts_resolved."
    )
    return "\n".join(sections)


def _parse_judge_output(
    raw_output: str,
    worker_results: dict[str, WorkerResult],
    total_cost: float,
) -> FinalOutput:
    json_match = re.search(r"\{[\s\S]*\}", raw_output)
    if not json_match:
        return FinalOutput(
            summary="Failed to parse judge output",
            worker_results=worker_results,
            metadata={"raw_judge_output": raw_output, "total_cost_usd": total_cost},
        )

    try:
        data = json.loads(json_match.group())
        risk_report = []
        for f in data.get("risk_report", []):
            try:
                risk_report.append(Finding(**f))
            except Exception:
                pass

        return FinalOutput(
            summary=data.get("summary", ""),
            risk_report=risk_report,
            patch=data.get("patch"),
            pr_summary=data.get("pr_summary", ""),
            worker_results=worker_results,
            conflicts_resolved=data.get("conflicts_resolved", []),
            metadata={"total_cost_usd": total_cost},
        )
    except (json.JSONDecodeError, Exception) as e:
        return FinalOutput(
            summary=f"Judge output parse error: {e}",
            worker_results=worker_results,
            metadata={"raw_judge_output": raw_output, "total_cost_usd": total_cost},
        )
