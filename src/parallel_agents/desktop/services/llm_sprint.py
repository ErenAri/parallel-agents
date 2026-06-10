"""LLM-backed SprintPlan generation via structured tool-use output.

Sprint items are derived deterministically from the roadmap's milestone (that
mapping is correct, not theater); the LLM rewrites the sprint goals and risks so
they are specific to the milestone scope rather than generic.
"""

from __future__ import annotations

from parallel_agents.company_workflows import (
    RoadmapPlan,
    SprintPlan,
    build_sprint_plan,
)
from parallel_agents.desktop.services.llm import call_anthropic_tool, str_list

_SCHEMA = {
    "type": "object",
    "properties": {
        "goals": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["goals"],
}

_PROMPT = """You are the delivery agent in an AI software office.
For milestone "{milestone}" of this roadmap, write 2-4 concrete sprint goals and
2-4 realistic risks, specific to the scope below.

Milestone: {milestone}
Roadmap JSON:
{roadmap_json}
"""


def generate_llm_sprint(
    roadmap: RoadmapPlan, *, milestone: str, horizon_days: int = 14
) -> tuple[SprintPlan, str]:
    # Deterministic derivation of items from the roadmap milestone (raises
    # ValueError if the milestone has no items — caller falls back).
    base = build_sprint_plan(roadmap, milestone=milestone, horizon_days=horizon_days)
    payload, model = call_anthropic_tool(
        _PROMPT.format(milestone=milestone, roadmap_json=roadmap.model_dump_json(indent=2)),
        tool_name="emit_sprint_plan",
        tool_description="Return the structured sprint goals and risks.",
        input_schema=_SCHEMA,
        max_tokens=1500,
    )
    plan = SprintPlan(
        name=base.name,
        milestone=base.milestone,
        horizon_days=base.horizon_days,
        goals=str_list(payload.get("goals"), base.goals),
        items=base.items,
        risks=str_list(payload.get("risks"), base.risks),
    )
    return plan, model
