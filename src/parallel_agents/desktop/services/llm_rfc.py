"""LLM-backed Architecture RFC generation via structured tool-use output."""

from __future__ import annotations

from parallel_agents.company_workflows import (
    ArchitectureRFC,
    ProductBrief,
    TechStackDecision,
    build_architecture_rfc,
)
from parallel_agents.desktop.services.llm import call_anthropic_tool, str_list, text_or

_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "context": {"type": "string"},
        "decision": {"type": "string"},
        "alternatives": {"type": "array", "items": {"type": "string"}},
        "tradeoffs": {"type": "array", "items": {"type": "string"}},
        "security_considerations": {"type": "array", "items": {"type": "string"}},
        "rollout_plan": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "context", "decision"],
}

_PROMPT = """You are the architecture agent in an AI software office.
Draft an Architecture RFC informed by the ProductBrief and TechStackDecision.
Be decisive in the decision field. 2-4 alternatives, 2-4 honest tradeoffs,
3-5 phased rollout steps. Be specific to these inputs.

ProductBrief JSON:
{brief_json}

TechStackDecision JSON:
{stack_json}
"""


def generate_llm_rfc(
    brief: ProductBrief, stack: TechStackDecision
) -> tuple[ArchitectureRFC, str]:
    payload, model = call_anthropic_tool(
        _PROMPT.format(
            brief_json=brief.model_dump_json(indent=2),
            stack_json=stack.model_dump_json(indent=2),
        ),
        tool_name="emit_architecture_rfc",
        tool_description="Return the structured Architecture RFC.",
        input_schema=_SCHEMA,
        max_tokens=3000,
    )
    fallback = build_architecture_rfc(brief, stack)
    rfc = ArchitectureRFC(
        id=fallback.id,
        title=text_or(payload.get("title"), fallback.title),
        context=text_or(payload.get("context"), fallback.context),
        decision=text_or(payload.get("decision"), fallback.decision),
        alternatives=str_list(payload.get("alternatives"), fallback.alternatives),
        tradeoffs=str_list(payload.get("tradeoffs"), fallback.tradeoffs),
        security_considerations=str_list(
            payload.get("security_considerations"), fallback.security_considerations
        ),
        rollout_plan=str_list(payload.get("rollout_plan"), fallback.rollout_plan),
    )
    return rfc, model
