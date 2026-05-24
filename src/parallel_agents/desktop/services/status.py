"""Pure-logic helpers used by the status bar. No Qt imports."""

from __future__ import annotations

import os


def llm_indicator_text() -> str:
    flags = {
        "brief": _truthy("PA_DESKTOP_LLM_BRIEF"),
        "prfaq": _truthy("PA_DESKTOP_LLM_PRFAQ"),
        "rfc": _truthy("PA_DESKTOP_LLM_RFC"),
    }
    enabled = [name for name, on in flags.items() if on]
    if not enabled:
        return "LLM: deterministic"
    return "LLM: " + ", ".join(enabled)


def _truthy(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}
