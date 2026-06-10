"""LLM-backed ProductBrief generation via structured tool-use output."""

from __future__ import annotations

from parallel_agents.company_workflows import ProductBrief, create_product_brief
from parallel_agents.desktop.services.llm import call_anthropic_tool, str_list, text_or

_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "problem_statement": {"type": "string"},
        "target_users": {"type": "array", "items": {"type": "string"}},
        "goals": {"type": "array", "items": {"type": "string"}},
        "non_goals": {"type": "array", "items": {"type": "string"}},
        "success_metrics": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "problem_statement", "goals"],
}

_PROMPT = """You are the product agent in an AI software office.
Produce a focused ProductBrief for this idea. Be specific to the idea — do not
return generic boilerplate.

Idea: {idea}
Suggested title (use if reasonable): {title_hint}
"""


def generate_llm_brief(idea: str, *, title: str | None = None) -> tuple[ProductBrief, str]:
    payload, model = call_anthropic_tool(
        _PROMPT.format(idea=idea, title_hint=title or "(none)"),
        tool_name="emit_product_brief",
        tool_description="Return the structured ProductBrief for the idea.",
        input_schema=_SCHEMA,
    )
    base = create_product_brief(idea, title=text_or(payload.get("title"), title or ""))
    brief = ProductBrief(
        id=base.id,
        title=text_or(payload.get("title"), title or base.title),
        idea=idea,
        problem_statement=text_or(payload.get("problem_statement"), base.problem_statement),
        target_users=str_list(payload.get("target_users"), base.target_users),
        goals=str_list(payload.get("goals"), base.goals),
        non_goals=str_list(payload.get("non_goals"), base.non_goals),
        success_metrics=str_list(payload.get("success_metrics"), base.success_metrics),
        assumptions=str_list(payload.get("assumptions"), base.assumptions),
        unknowns=str_list(payload.get("unknowns"), base.unknowns),
    )
    return brief, model
