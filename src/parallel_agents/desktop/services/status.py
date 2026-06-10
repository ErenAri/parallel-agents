"""Pure-logic helpers used by the status bar. No Qt imports."""

from __future__ import annotations

from parallel_agents.desktop.services.llm_config import ARTIFACTS, active_generators


def llm_indicator_text() -> str:
    active = active_generators()
    if not active:
        return "LLM: deterministic"
    if len(active) == len(ARTIFACTS):
        return "LLM: all"
    return "LLM: " + ", ".join(active)
