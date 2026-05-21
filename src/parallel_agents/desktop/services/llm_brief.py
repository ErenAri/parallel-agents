"""LLM-backed ProductBrief generation. Falls back to deterministic on any error."""

from __future__ import annotations

from parallel_agents.company_workflows import ProductBrief, create_product_brief
from parallel_agents.desktop.services.llm import call_anthropic, extract_json

PROMPT_TEMPLATE = """You are the product agent in an AI software office.

Produce a ProductBrief for the following idea. Respond with a single JSON object
matching this schema (no prose, no markdown fences):

{{
  "title": str,
  "problem_statement": str,
  "target_users": [str, ...],
  "goals": [str, ...],
  "non_goals": [str, ...],
  "success_metrics": [str, ...],
  "assumptions": [str, ...],
  "unknowns": [str, ...]
}}

Idea: {idea}
Hint title (use if reasonable): {title_hint}
"""


def generate_llm_brief(idea: str, *, title: str | None = None) -> ProductBrief:
    raw = call_anthropic(PROMPT_TEMPLATE.format(idea=idea, title_hint=title or "(none)"))
    payload = extract_json(raw)
    base = create_product_brief(idea, title=payload.get("title") or title)
    return ProductBrief(
        id=base.id,
        title=payload.get("title") or title or base.title,
        idea=idea,
        problem_statement=str(payload.get("problem_statement") or base.problem_statement),
        target_users=list(payload.get("target_users") or base.target_users),
        goals=list(payload.get("goals") or base.goals),
        non_goals=list(payload.get("non_goals") or base.non_goals),
        success_metrics=list(payload.get("success_metrics") or base.success_metrics),
        assumptions=list(payload.get("assumptions") or base.assumptions),
        unknowns=list(payload.get("unknowns") or base.unknowns),
    )
