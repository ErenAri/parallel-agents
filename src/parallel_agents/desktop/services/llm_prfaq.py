"""LLM-backed PR/FAQ generation via structured tool-use output."""

from __future__ import annotations

from parallel_agents.company_workflows import (
    FAQItem,
    PRFAQDocument,
    ProductBrief,
    build_prfaq,
)
from parallel_agents.desktop.services.llm import call_anthropic_tool, str_list, text_or

_FAQ_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "answer": {"type": "string"},
        },
        "required": ["question", "answer"],
    },
}

_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "press_release_summary": {"type": "string"},
        "customer_faq": _FAQ_SCHEMA,
        "internal_faq": _FAQ_SCHEMA,
        "launch_criteria": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "press_release_summary", "customer_faq"],
}

_PROMPT = """You are the launch communications agent in an AI software office.
Produce a PR/FAQ for the product in this ProductBrief. 4-6 customer FAQ entries,
3-5 internal FAQ entries, 4-6 measurable launch criteria. Be specific to the brief.

ProductBrief JSON:
{brief_json}
"""


def generate_llm_prfaq(brief: ProductBrief) -> tuple[PRFAQDocument, str]:
    payload, model = call_anthropic_tool(
        _PROMPT.format(brief_json=brief.model_dump_json(indent=2)),
        tool_name="emit_prfaq",
        tool_description="Return the structured PR/FAQ document for the product.",
        input_schema=_SCHEMA,
        max_tokens=2500,
    )
    fallback = build_prfaq(brief)
    doc = PRFAQDocument(
        headline=text_or(payload.get("headline"), fallback.headline),
        press_release_summary=text_or(
            payload.get("press_release_summary"), fallback.press_release_summary
        ),
        customer_faq=_coerce_faq(payload.get("customer_faq"), fallback.customer_faq),
        internal_faq=_coerce_faq(payload.get("internal_faq"), fallback.internal_faq),
        launch_criteria=str_list(payload.get("launch_criteria"), fallback.launch_criteria),
    )
    return doc, model


def _coerce_faq(value, fallback) -> list[FAQItem]:
    if not isinstance(value, list) or not value:
        return list(fallback)
    items: list[FAQItem] = []
    for entry in value:
        if isinstance(entry, dict) and "question" in entry and "answer" in entry:
            items.append(
                FAQItem(question=str(entry["question"]), answer=str(entry["answer"]))
            )
    return items or list(fallback)
