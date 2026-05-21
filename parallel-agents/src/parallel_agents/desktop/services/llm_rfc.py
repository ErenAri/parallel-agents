"""LLM-backed Architecture RFC generation. Falls back to deterministic on any error."""

from __future__ import annotations

from parallel_agents.company_workflows import (
    ArchitectureRFC,
    ProductBrief,
    TechStackDecision,
    build_architecture_rfc,
)
from parallel_agents.desktop.services.llm import call_anthropic, extract_json

PROMPT_TEMPLATE = """You are the architecture agent in an AI software office.

Draft an Architecture RFC informed by the ProductBrief and TechStackDecision
below. Respond with a single JSON object matching this schema (no prose, no
fences):

{{
  "title": str,
  "context": str,                       # restate the problem and constraints
  "decision": str,                      # 1-3 sentences, decisive
  "alternatives": [str, ...],           # 2-4 alternatives considered
  "tradeoffs": [str, ...],              # 2-4 honest tradeoffs of the chosen decision
  "security_considerations": [str, ...],
  "rollout_plan": [str, ...]            # 3-5 phased rollout steps
}}

ProductBrief JSON:
{brief_json}

TechStackDecision JSON:
{stack_json}
"""


def generate_llm_rfc(brief: ProductBrief, stack: TechStackDecision) -> ArchitectureRFC:
    raw = call_anthropic(
        PROMPT_TEMPLATE.format(
            brief_json=brief.model_dump_json(indent=2),
            stack_json=stack.model_dump_json(indent=2),
        ),
        max_tokens=2500,
    )
    payload = extract_json(raw)
    fallback = build_architecture_rfc(brief, stack)
    return ArchitectureRFC(
        id=fallback.id,
        title=str(payload.get("title") or fallback.title),
        context=str(payload.get("context") or fallback.context),
        decision=str(payload.get("decision") or fallback.decision),
        alternatives=list(payload.get("alternatives") or fallback.alternatives),
        tradeoffs=list(payload.get("tradeoffs") or fallback.tradeoffs),
        security_considerations=list(
            payload.get("security_considerations") or fallback.security_considerations
        ),
        rollout_plan=list(payload.get("rollout_plan") or fallback.rollout_plan),
    )
