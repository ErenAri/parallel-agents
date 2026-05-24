"""Shared LLM client used by llm_brief / llm_prfaq / llm_rfc generators.

Every call is wrapped in tight error handling at the generator level so a
missing key or SDK or a malformed response falls back to the deterministic
artifact without surfacing to the UI.
"""

from __future__ import annotations

import json
import os
import re


def call_anthropic(prompt: str, *, max_tokens: int = 1500, model_env: str = "PA_DESKTOP_BRIEF_MODEL") -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise RuntimeError("anthropic SDK not installed") from exc

    client = Anthropic(api_key=api_key)
    model = os.environ.get(model_env) or os.environ.get(
        "PA_DESKTOP_LLM_MODEL", "claude-sonnet-4-6"
    )
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = [b.text for b in response.content if getattr(b, "type", "") == "text"]
    if not parts:
        raise RuntimeError("Empty response from Anthropic API")
    return "".join(parts)


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*", "", text).rstrip("`").strip()
    return json.loads(text)


def truthy(value: str | None) -> bool:
    return bool(value) and value.strip().lower() in {"1", "true", "yes", "on"}
