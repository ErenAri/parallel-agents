"""Unit tests for cost tracker."""

from __future__ import annotations

from parallel_agents.cost_tracker import PipelineCostTracker


class TestPipelineCostTracker:
    def test_empty(self):
        tracker = PipelineCostTracker()
        assert tracker.total_tokens == 0
        assert tracker.total_cost_usd == 0.0

    def test_record_usage(self):
        tracker = PipelineCostTracker()
        tracker.record_usage(
            agent_name="security",
            model="sonnet",
            usage={"input_tokens": 1000, "output_tokens": 500},
            cost_usd=0.01,
            duration_ms=5000,
        )
        assert tracker.total_input_tokens == 1000
        assert tracker.total_output_tokens == 500
        assert tracker.total_tokens == 1500
        assert tracker.total_cost_usd == 0.01
        assert tracker.total_duration_ms == 5000

    def test_multiple_agents(self):
        tracker = PipelineCostTracker()
        tracker.record_usage("security", "sonnet", {"input_tokens": 1000, "output_tokens": 200}, cost_usd=0.01)
        tracker.record_usage("code", "opus", {"input_tokens": 5000, "output_tokens": 3000}, cost_usd=0.10)
        tracker.record_usage("review", "sonnet", {"input_tokens": 800, "output_tokens": 400}, cost_usd=0.005)

        assert tracker.total_input_tokens == 6800
        assert tracker.total_output_tokens == 3600
        assert len(tracker.agent_usages) == 3

    def test_estimate_cost(self):
        tracker = PipelineCostTracker()
        tracker.record_usage("test", "sonnet", {"input_tokens": 1_000_000, "output_tokens": 1_000_000})
        estimated = tracker.estimate_cost("test")
        # sonnet: $3/M input + $15/M output = $18
        assert estimated == pytest.approx(18.0, rel=0.01)

    def test_summary(self):
        tracker = PipelineCostTracker()
        tracker.record_usage("security", "sonnet", {"input_tokens": 100, "output_tokens": 50}, cost_usd=0.001, duration_ms=2000)

        summary = tracker.summary()
        assert "agents" in summary
        assert "security" in summary["agents"]
        assert summary["total_tokens"] == 150
        assert summary["total_duration_ms"] == 2000


import pytest  # noqa: E402 - needed for approx
