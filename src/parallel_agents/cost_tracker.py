"""Token usage tracking and cost estimation across the pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("parallel_agents.cost")

# Pricing per 1M tokens (USD) — update as pricing changes
MODEL_PRICING: dict[str, dict[str, float]] = {
    "opus": {"input": 15.0, "output": 75.0},
    "sonnet": {"input": 3.0, "output": 15.0},
    "haiku": {"input": 0.25, "output": 1.25},
    # Claude 4 family
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    "claude-haiku-4-20250514": {"input": 0.25, "output": 1.25},
}


@dataclass
class AgentUsage:
    agent_name: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0


@dataclass
class PipelineCostTracker:
    """Tracks token usage and costs across all agents in a pipeline run."""

    agent_usages: dict[str, AgentUsage] = field(default_factory=dict)

    def record_usage(
        self,
        agent_name: str,
        model: str,
        usage: dict[str, Any] | None = None,
        cost_usd: float = 0.0,
        duration_ms: int = 0,
    ) -> None:
        """Record usage from a single agent run."""
        if agent_name not in self.agent_usages:
            self.agent_usages[agent_name] = AgentUsage(agent_name=agent_name)

        au = self.agent_usages[agent_name]
        au.model = model

        if usage:
            au.input_tokens += usage.get("input_tokens", 0)
            au.output_tokens += usage.get("output_tokens", 0)
            au.cache_read_tokens += usage.get("cache_read_input_tokens", 0)
            au.cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)

        au.cost_usd += cost_usd
        au.duration_ms += duration_ms

    def estimate_cost(self, agent_name: str) -> float:
        """Estimate cost for an agent based on token counts and model pricing."""
        au = self.agent_usages.get(agent_name)
        if not au:
            return 0.0

        pricing = _get_pricing(au.model)
        if not pricing:
            return au.cost_usd  # fall back to reported cost

        input_cost = (au.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (au.output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    @property
    def total_input_tokens(self) -> int:
        return sum(au.input_tokens for au in self.agent_usages.values())

    @property
    def total_output_tokens(self) -> int:
        return sum(au.output_tokens for au in self.agent_usages.values())

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def total_cost_usd(self) -> float:
        return sum(au.cost_usd for au in self.agent_usages.values())

    @property
    def total_estimated_cost_usd(self) -> float:
        return sum(self.estimate_cost(name) for name in self.agent_usages)

    @property
    def total_duration_ms(self) -> int:
        return sum(au.duration_ms for au in self.agent_usages.values())

    def summary(self) -> dict[str, Any]:
        """Return a summary dict suitable for the manifest or display."""
        agents = {}
        for name, au in self.agent_usages.items():
            agents[name] = {
                "model": au.model,
                "input_tokens": au.input_tokens,
                "output_tokens": au.output_tokens,
                "cache_read_tokens": au.cache_read_tokens,
                "cost_usd": round(au.cost_usd, 6),
                "estimated_cost_usd": round(self.estimate_cost(name), 6),
                "duration_ms": au.duration_ms,
            }
        return {
            "agents": agents,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_estimated_cost_usd": round(self.total_estimated_cost_usd, 6),
            "total_duration_ms": self.total_duration_ms,
        }


def _get_pricing(model: str) -> dict[str, float] | None:
    """Look up pricing for a model name (exact or fuzzy match)."""
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # Try fuzzy: "opus" matches any key containing "opus"
    model_lower = model.lower()
    for key, pricing in MODEL_PRICING.items():
        if key in model_lower or model_lower in key:
            return pricing
    return None
