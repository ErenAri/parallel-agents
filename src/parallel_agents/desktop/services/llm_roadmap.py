"""LLM-backed RoadmapPlan generation via structured tool-use output.

This replaces the single biggest source of "template theater": the deterministic
builder returned the same four roadmap items (about building parallel-agents
itself) for every idea. Here the items are generated from the actual brief.
"""

from __future__ import annotations

from parallel_agents.company_workflows import (
    ProductBrief,
    RoadmapItem,
    RoadmapPlan,
    build_roadmap,
)
from parallel_agents.desktop.services.llm import call_anthropic_tool, str_list, text_or

_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "owner_role": {"type": "string"},
        "milestone": {"type": "string"},
        "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
        "dependencies": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "owner_role", "milestone"],
}

_SCHEMA = {
    "type": "object",
    "properties": {
        "outcomes": {"type": "array", "items": {"type": "string"}},
        "items": {"type": "array", "items": _ITEM_SCHEMA},
    },
    "required": ["items"],
}

_PROMPT = """You are the planning agent in an AI software office.
Produce a delivery roadmap for the product in this ProductBrief over about
{weeks} weeks. Generate 4-8 concrete roadmap items SPECIFIC to this product —
not generic process steps. Group them into milestones (e.g. M1, M2, M3). Each
item needs a clear title, an owner role, a milestone, and acceptance criteria.

ProductBrief JSON:
{brief_json}
"""


def generate_llm_roadmap(
    brief: ProductBrief, horizon_weeks: int = 12
) -> tuple[RoadmapPlan, str]:
    weeks = max(1, horizon_weeks)
    payload, model = call_anthropic_tool(
        _PROMPT.format(weeks=weeks, brief_json=brief.model_dump_json(indent=2)),
        tool_name="emit_roadmap",
        tool_description="Return the structured delivery roadmap for the product.",
        input_schema=_SCHEMA,
        max_tokens=3000,
    )
    items = _coerce_items(payload.get("items"))
    if not items:
        # Don't pass off the deterministic template as LLM output — that is the
        # exact "template theater" this module exists to avoid. Raising routes
        # through the engine's fallback path so provenance is recorded as
        # template, not llm.
        raise RuntimeError("roadmap LLM returned no usable items")
    fallback = build_roadmap(brief, horizon_weeks=weeks)
    return (
        RoadmapPlan(
            name=f"{brief.title} Roadmap",
            horizon_weeks=weeks,
            outcomes=str_list(payload.get("outcomes"), fallback.outcomes),
            items=items,
        ),
        model,
    )


def _coerce_items(value) -> list[RoadmapItem]:
    if not isinstance(value, list):
        return []
    items: list[RoadmapItem] = []
    for idx, entry in enumerate(value, start=1):
        if not isinstance(entry, dict):
            continue
        title = text_or(entry.get("title"), "")
        if not title:
            continue
        items.append(
            RoadmapItem(
                id=text_or(entry.get("id"), f"RM-{idx:02d}"),
                title=title,
                owner_role=text_or(entry.get("owner_role"), "Product Agent"),
                milestone=text_or(entry.get("milestone"), "M1"),
                acceptance_criteria=str_list(entry.get("acceptance_criteria"), []),
                dependencies=str_list(entry.get("dependencies"), []),
            )
        )
    return items
