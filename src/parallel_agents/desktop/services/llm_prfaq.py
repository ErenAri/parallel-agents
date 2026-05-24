"""LLM-backed PR/FAQ generation. Falls back to deterministic on any error."""

from __future__ import annotations

from parallel_agents.company_workflows import (
    FAQItem,
    PRFAQDocument,
    ProductBrief,
    build_prfaq,
)
from parallel_agents.desktop.services.llm import call_anthropic, extract_json

PROMPT_TEMPLATE = """You are the launch communications agent in an AI software office.

Produce a PR/FAQ document for the product described in the ProductBrief below.
Respond with a single JSON object matching this schema (no prose, no fences):

{{
  "headline": str,
  "press_release_summary": str,
  "customer_faq": [{{"question": str, "answer": str}}, ...],   # 4-6 entries
  "internal_faq": [{{"question": str, "answer": str}}, ...],   # 3-5 entries
  "launch_criteria": [str, ...]                                # 4-6 measurable gates
}}

ProductBrief JSON:
{brief_json}
"""


def generate_llm_prfaq(brief: ProductBrief) -> PRFAQDocument:
    raw = call_anthropic(
        PROMPT_TEMPLATE.format(brief_json=brief.model_dump_json(indent=2)),
        max_tokens=2000,
    )
    payload = extract_json(raw)
    fallback = build_prfaq(brief)
    return PRFAQDocument(
        headline=str(payload.get("headline") or fallback.headline),
        press_release_summary=str(
            payload.get("press_release_summary") or fallback.press_release_summary
        ),
        customer_faq=_coerce_faq(payload.get("customer_faq"), fallback.customer_faq),
        internal_faq=_coerce_faq(payload.get("internal_faq"), fallback.internal_faq),
        launch_criteria=list(payload.get("launch_criteria") or fallback.launch_criteria),
    )


def _coerce_faq(value, fallback):
    if not isinstance(value, list) or not value:
        return list(fallback)
    items = []
    for entry in value:
        if isinstance(entry, dict) and "question" in entry and "answer" in entry:
            items.append(FAQItem(question=str(entry["question"]), answer=str(entry["answer"])))
    return items or list(fallback)
