"""Unit tests for the task splitter — dependency resolution and batching."""

from __future__ import annotations

from parallel_agents.agents.splitter import split_tasks
from parallel_agents.config import PipelineConfig, WorkerConfig
from parallel_agents.models import Subtask, TaskPlan


def _plan(*subtasks: Subtask) -> TaskPlan:
    return TaskPlan(summary="test", subtasks=list(subtasks))


class TestSplitTasks:
    def test_empty_plan(self):
        plan = _plan()
        config = PipelineConfig()
        batches = split_tasks(plan, config)
        assert batches == []

    def test_single_subtask(self):
        plan = _plan(Subtask(id="s1", description="scan", assigned_worker="security"))
        config = PipelineConfig()
        batches = split_tasks(plan, config)
        assert len(batches) == 1
        assert len(batches[0]) == 1
        assert batches[0][0].assigned_worker == "security"

    def test_independent_subtasks_same_batch(self):
        plan = _plan(
            Subtask(id="s1", description="scan", assigned_worker="security"),
            Subtask(id="s2", description="code", assigned_worker="code"),
            Subtask(id="s3", description="review", assigned_worker="review"),
        )
        config = PipelineConfig()
        batches = split_tasks(plan, config)
        assert len(batches) == 1
        assert len(batches[0]) == 3

    def test_dependent_subtasks_separate_batches(self):
        plan = _plan(
            Subtask(id="s1", description="code", assigned_worker="code"),
            Subtask(id="s2", description="review", assigned_worker="review", dependencies=["s1"]),
        )
        config = PipelineConfig()
        batches = split_tasks(plan, config)
        assert len(batches) == 2
        assert batches[0][0].assigned_worker == "code"
        assert batches[1][0].assigned_worker == "review"

    def test_chain_dependencies(self):
        plan = _plan(
            Subtask(id="s1", description="code", assigned_worker="code"),
            Subtask(id="s2", description="test", assigned_worker="test", dependencies=["s1"]),
            Subtask(id="s3", description="review", assigned_worker="review", dependencies=["s2"]),
        )
        config = PipelineConfig()
        batches = split_tasks(plan, config)
        assert len(batches) == 3
        assert batches[0][0].id == "s1"
        assert batches[1][0].id == "s2"
        assert batches[2][0].id == "s3"

    def test_mixed_dependencies(self):
        """s1, s2 independent; s3 depends on s1; s4 depends on s2."""
        plan = _plan(
            Subtask(id="s1", description="security", assigned_worker="security"),
            Subtask(id="s2", description="code", assigned_worker="code"),
            Subtask(id="s3", description="review", assigned_worker="review", dependencies=["s1"]),
            Subtask(id="s4", description="test", assigned_worker="test", dependencies=["s2"]),
        )
        config = PipelineConfig()
        batches = split_tasks(plan, config)
        assert len(batches) == 2
        batch1_workers = {s.assigned_worker for s in batches[0]}
        batch2_workers = {s.assigned_worker for s in batches[1]}
        assert "security" in batch1_workers
        assert "code" in batch1_workers
        assert "review" in batch2_workers
        assert "test" in batch2_workers

    def test_disabled_workers_filtered(self):
        plan = _plan(
            Subtask(id="s1", description="scan", assigned_worker="security"),
            Subtask(id="s2", description="code", assigned_worker="code"),
            Subtask(id="s3", description="perf", assigned_worker="perf"),
        )
        config = PipelineConfig(workers={
            "security": WorkerConfig(enabled=True),
            "code": WorkerConfig(enabled=True),
            "perf": WorkerConfig(enabled=False),
            "test": WorkerConfig(enabled=True),
            "devops": WorkerConfig(enabled=True),
            "arch": WorkerConfig(enabled=True),
            "docs": WorkerConfig(enabled=True),
            "review": WorkerConfig(enabled=True),
        })
        batches = split_tasks(plan, config)
        all_workers = [s.assigned_worker for b in batches for s in b]
        assert "perf" not in all_workers
        assert "security" in all_workers
        assert "code" in all_workers

    def test_priority_ordering(self):
        plan = _plan(
            Subtask(id="s1", description="low", assigned_worker="docs", priority=0),
            Subtask(id="s2", description="high", assigned_worker="security", priority=10),
            Subtask(id="s3", description="medium", assigned_worker="review", priority=5),
        )
        config = PipelineConfig()
        batches = split_tasks(plan, config)
        assert len(batches) == 1
        # Higher priority first
        assert batches[0][0].assigned_worker == "security"
        assert batches[0][1].assigned_worker == "review"
        assert batches[0][2].assigned_worker == "docs"

    def test_dependency_on_disabled_worker(self):
        """If s2 depends on s1, but s1's worker is disabled, s2 should still run."""
        plan = _plan(
            Subtask(id="s1", description="perf", assigned_worker="perf"),
            Subtask(id="s2", description="code", assigned_worker="code", dependencies=["s1"]),
        )
        config = PipelineConfig(workers={
            "security": WorkerConfig(enabled=True),
            "code": WorkerConfig(enabled=True),
            "perf": WorkerConfig(enabled=False),
            "test": WorkerConfig(enabled=True),
            "devops": WorkerConfig(enabled=True),
            "arch": WorkerConfig(enabled=True),
            "docs": WorkerConfig(enabled=True),
            "review": WorkerConfig(enabled=True),
        })
        batches = split_tasks(plan, config)
        all_workers = [s.assigned_worker for b in batches for s in b]
        assert "code" in all_workers
        assert "perf" not in all_workers
