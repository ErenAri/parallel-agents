"""Shared Anthropic client for the desktop artifact generators.

Every generator forces structured output via tool-use, so the model returns a
schema-validated dict — no regex JSON extraction and no `list("string")`
character-explosion bug. Each call has a short timeout and a single retry; any
failure raises RuntimeError and the caller falls back to the deterministic
builder.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("parallel_agents.desktop.llm")

# Sonnet is the right tier for these small (~2KB) structured generations:
# fast and inexpensive, with strong instruction-following. Override with
# PA_DESKTOP_LLM_MODEL.
DEFAULT_MODEL = "claude-sonnet-4-6"
_TIMEOUT_SECONDS = 45.0


def resolve_model() -> str:
    return (
        os.environ.get("PA_DESKTOP_LLM_MODEL")
        or os.environ.get("PA_DESKTOP_BRIEF_MODEL")
        or DEFAULT_MODEL
    )


def call_anthropic_tool(
    prompt: str,
    *,
    tool_name: str,
    tool_description: str,
    input_schema: dict,
    max_tokens: int = 2000,
) -> tuple[dict, str]:
    """Force the model to emit a structured object via tool-use.

    Returns ``(validated_input_dict, model_id)``. Raises RuntimeError on any
    failure (missing key, missing SDK, network/API error, or no tool_use block).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover - depends on optional dep
        raise RuntimeError("anthropic SDK not installed") from exc

    model = resolve_model()
    client = Anthropic(api_key=api_key).with_options(
        timeout=_TIMEOUT_SECONDS, max_retries=1
    )
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[
            {
                "name": tool_name,
                "description": tool_description,
                "input_schema": input_schema,
            }
        ],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if getattr(block, "type", "") == "tool_use" and getattr(block, "name", "") == tool_name:
            data = block.input
            if isinstance(data, dict):
                return data, model
    raise RuntimeError("Model did not return the expected structured output")


def str_list(value, fallback) -> list[str]:
    """Coerce to list[str] WITHOUT exploding a bare string into characters.

    The old ``list(payload.get(...))`` pattern turned a stray string like
    "increase adoption" into ['i','n','c',...]; this never does that.
    """
    if isinstance(value, list):
        cleaned = [
            str(v).strip()
            for v in value
            if v is not None and str(v).strip()
        ]
        return cleaned or list(fallback)
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return list(fallback)


def text_or(value, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return str(fallback)
