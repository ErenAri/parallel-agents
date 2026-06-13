"""LLM-backed TechStackDecision generation via structured tool-use output.

The deterministic option-scoring rubric and repo-signal detection stay (they are
real analysis); the LLM enriches the narrative — context, constraints,
recommended option, rationale, and risks — so the decision reflects the actual
product idea rather than a fixed template.
"""

from __future__ import annotations

from pathlib import Path

from parallel_agents.company_workflows import (
    ProductBrief,
    TechStackDecision,
    recommend_tech_stack,
)
from parallel_agents.desktop.services.llm import call_anthropic_tool, str_list, text_or

_SCHEMA = {
    "type": "object",
    "properties": {
        "context": {"type": "string"},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "recommended_option": {"type": "string"},
        "rationale": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["recommended_option", "rationale"],
}

_PROMPT = """You are the tech-stack agent in an AI software office.
Recommend a stack for the product in this ProductBrief, grounded in the detected
repository signals. Give a decisive recommended_option, a rationale specific to
the idea, realistic constraints, and honest risks.

ProductBrief JSON:
{brief_json}

Detected repository signals: {signals}
"""


def generate_llm_tech_stack(
    brief: ProductBrief, repo_path: str | Path
) -> tuple[TechStackDecision, str]:
    base = recommend_tech_stack(repo_path)
    payload, model = call_anthropic_tool(
        _PROMPT.format(
            brief_json=brief.model_dump_json(indent=2),
            signals=", ".join(base.detected_signals) or "(none detected)",
        ),
        tool_name="emit_tech_stack_decision",
        tool_description="Return the structured tech-stack decision narrative.",
        input_schema=_SCHEMA,
        max_tokens=2000,
    )
    decision = TechStackDecision(
        context=text_or(payload.get("context"), base.context),
        constraints=str_list(payload.get("constraints"), base.constraints),
        options=base.options,  # keep the deterministic scoring rubric
        recommended_option=text_or(payload.get("recommended_option"), base.recommended_option),
        rationale=text_or(payload.get("rationale"), base.rationale),
        risks=str_list(payload.get("risks"), base.risks),
        detected_signals=base.detected_signals,
    )
    return decision, model
