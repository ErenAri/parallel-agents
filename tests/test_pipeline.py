"""Integration tests for pipeline with mocked SDK query() calls."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from parallel_agents.config import PipelineConfig, WorkerConfig
from parallel_agents.models import FinalOutput
from parallel_agents.pipeline import Pipeline


def _mock_planner_response() -> str:
    """Return a mock planner JSON response."""
    return json.dumps({
        "summary": "Test plan for mock repo",
        "repo_analysis": {"languages": ["python"], "frameworks": ["flask"]},
        "subtasks": [
            {
                "id": "s1",
                "description": "Security scan",
                "assigned_worker": "security",
                "context": {},
                "dependencies": [],
                "priority": 1,
            },
            {
                "id": "s2",
                "description": "Code review",
                "assigned_worker": "review",
                "context": {},
                "dependencies": [],
                "priority": 0,
            },
        ],
        "global_context": {"repo_path": "/tmp/mock-repo", "task_summary": "test"},
    })


def _mock_worker_response(worker_name: str) -> str:
    """Return a mock worker JSON response."""
    return json.dumps({
        "findings": [
            {
                "severity": "medium",
                "category": "test",
                "title": f"{worker_name} finding",
                "description": f"Found by {worker_name}",
                "file_path": "src/main.py",
            }
        ],
        "recommendations": [
            {
                "type": "code_change",
                "description": f"{worker_name} recommendation",
                "file_path": "src/main.py",
                "suggested_content": "# fixed code",
                "rationale": "best practice",
                "priority": "should",
            }
        ],
    })


def _mock_judge_response() -> str:
    """Return a mock judge JSON response."""
    return json.dumps({
        "summary": "Analysis complete: 2 findings across 2 workers",
        "risk_report": [
            {
                "severity": "medium",
                "category": "test",
                "title": "security finding",
                "description": "Found by security",
            }
        ],
        "patch": "--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-old\n+new",
        "pr_summary": "## Summary\n- Fixed security issue\n- Improved code quality",
        "conflicts_resolved": [],
    })


from claude_code_sdk import AssistantMessage, TextBlock, ResultMessage


async def _mock_query_generator(response_text: str):
    """Create a mock async generator that yields real SDK message types."""
    yield AssistantMessage(content=[TextBlock(text=response_text)], model="sonnet")
    yield ResultMessage(
        subtype="result",
        duration_ms=1000,
        duration_api_ms=900,
        is_error=False,
        num_turns=1,
        session_id="mock-session",
        total_cost_usd=0.01,
        usage={"input_tokens": 1000, "output_tokens": 500},
        result=response_text,
    )


@pytest.mark.asyncio
async def test_pipeline_end_to_end():
    """Test full pipeline with mocked query() calls."""
    config = PipelineConfig(
        workers={
            "security": WorkerConfig(enabled=True),
            "review": WorkerConfig(enabled=True),
            # Disable others
            "code": WorkerConfig(enabled=False),
            "test": WorkerConfig(enabled=False),
            "perf": WorkerConfig(enabled=False),
            "devops": WorkerConfig(enabled=False),
            "arch": WorkerConfig(enabled=False),
            "docs": WorkerConfig(enabled=False),
        },
        store_backend="file",
    )

    call_count = 0
    responses = [
        _mock_planner_response(),           # planner
        _mock_worker_response("security"),  # security worker
        _mock_worker_response("review"),    # review worker
        _mock_judge_response(),             # judge
    ]

    def make_mock_query():
        """Create a mock query function that returns async generators."""
        counter = {"n": 0}

        def mock_query(*, prompt, options=None):
            idx = min(counter["n"], len(responses) - 1)
            text = responses[idx]
            counter["n"] += 1
            return _mock_query_generator(text)

        return mock_query

    mock_fn = make_mock_query()
    statuses: list[str] = []

    with patch("parallel_agents.agents.planner.query", new=mock_fn):
        with patch("parallel_agents.agents.base.query", new=mock_fn):
            with patch("parallel_agents.agents.judge.query", new=mock_fn):
                pipeline = Pipeline(config)
                result = await pipeline.run(
                    "Test the security and review",
                    repo_path="/tmp/mock-repo",
                    on_status=statuses.append,
                )

    assert isinstance(result, FinalOutput)
    assert result.summary != ""
    assert len(statuses) > 0  # Progress callbacks were called

    # Check cost tracking was recorded
    assert "cost" in result.metadata
    cost = result.metadata["cost"]
    assert cost["total_tokens"] >= 0


@pytest.mark.asyncio
async def test_pipeline_no_subtasks():
    """Test pipeline handles planner returning no subtasks."""
    config = PipelineConfig()

    empty_plan = json.dumps({
        "summary": "Nothing to do",
        "repo_analysis": {},
        "subtasks": [],
        "global_context": {},
    })

    def mock_query(*, prompt, options=None):
        return _mock_query_generator(empty_plan)

    with patch("parallel_agents.agents.planner.query", new=mock_query):
        pipeline = Pipeline(config)
        result = await pipeline.run("nothing", repo_path="/tmp/mock")

    assert "No subtasks" in result.summary
