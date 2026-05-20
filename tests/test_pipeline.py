"""Integration tests for pipeline with mocked SDK query() calls."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

from parallel_agents.config import PipelineConfig, WorkerConfig
from parallel_agents.models import FinalOutput
from parallel_agents.pipeline import Pipeline
from parallel_agents.tools.github_tools import GitHubIssue


def _single_review_config() -> PipelineConfig:
    return PipelineConfig(
        workers={
            "review": WorkerConfig(enabled=True),
            "security": WorkerConfig(enabled=False),
            "code": WorkerConfig(enabled=False),
            "test": WorkerConfig(enabled=False),
            "perf": WorkerConfig(enabled=False),
            "devops": WorkerConfig(enabled=False),
            "arch": WorkerConfig(enabled=False),
            "docs": WorkerConfig(enabled=False),
        },
        store_backend="file",
    )


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


def _mock_judge_invalid_patch_response() -> str:
    """Return a judge response with an invalid patch string."""
    return json.dumps({
        "summary": "Analysis complete with invalid patch",
        "risk_report": [],
        "patch": "not a unified diff",
        "pr_summary": "Summary",
        "conflicts_resolved": [],
    })


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


@pytest.mark.asyncio
async def test_pipeline_github_issue_fetch_failure_returns_error():
    """GitHub issue input should fail fast with clear error metadata if fetch fails."""
    config = PipelineConfig()
    pipeline = Pipeline(config)

    with patch("parallel_agents.pipeline.fetch_issue", new=AsyncMock(return_value=None)):
        result = await pipeline.run("https://github.com/org/repo/issues/42", repo_path="/tmp/mock")

    assert "Failed to fetch GitHub issue details" in result.summary
    assert result.metadata.get("error") == "github_issue_fetch_failed"


@pytest.mark.asyncio
async def test_pipeline_retries_planner_parse_failure():
    """Planner should retry once when first response is not valid JSON."""
    config = _single_review_config()
    responses = [
        "this is not valid planner json",
        json.dumps({
            "summary": "Recovered plan",
            "repo_analysis": {"languages": ["python"]},
            "subtasks": [{
                "id": "s1",
                "description": "Review code",
                "assigned_worker": "review",
                "context": {},
                "dependencies": [],
                "priority": 1,
            }],
            "global_context": {"repo_path": "/tmp/mock-repo"},
        }),
        _mock_worker_response("review"),
        _mock_judge_response(),
    ]
    counter = {"n": 0}

    def mock_query(*, prompt, options=None):
        idx = min(counter["n"], len(responses) - 1)
        counter["n"] += 1
        return _mock_query_generator(responses[idx])

    with patch("parallel_agents.agents.planner.query", new=mock_query):
        with patch("parallel_agents.agents.base.query", new=mock_query):
            with patch("parallel_agents.agents.judge.query", new=mock_query):
                pipeline = Pipeline(config)
                result = await pipeline.run("Review task", repo_path="/tmp/mock-repo")

    assert result.summary != ""
    assert counter["n"] == 4


@pytest.mark.asyncio
async def test_pipeline_retries_judge_parse_failure():
    """Judge should retry once when first response is not valid JSON."""
    config = _single_review_config()
    responses = [
        json.dumps({
            "summary": "Initial plan",
            "repo_analysis": {"languages": ["python"]},
            "subtasks": [{
                "id": "s1",
                "description": "Review code",
                "assigned_worker": "review",
                "context": {},
                "dependencies": [],
                "priority": 1,
            }],
            "global_context": {"repo_path": "/tmp/mock-repo"},
        }),
        _mock_worker_response("review"),
        "this is not valid judge json",
        _mock_judge_response(),
    ]
    counter = {"n": 0}

    def mock_query(*, prompt, options=None):
        idx = min(counter["n"], len(responses) - 1)
        counter["n"] += 1
        return _mock_query_generator(responses[idx])

    with patch("parallel_agents.agents.planner.query", new=mock_query):
        with patch("parallel_agents.agents.base.query", new=mock_query):
            with patch("parallel_agents.agents.judge.query", new=mock_query):
                pipeline = Pipeline(config)
                result = await pipeline.run("Review task", repo_path="/tmp/mock-repo")

    assert result.summary == "Analysis complete: 2 findings across 2 workers"
    assert counter["n"] == 4


@pytest.mark.asyncio
async def test_pipeline_retries_worker_parse_failure():
    """Worker should retry once when first response is not valid structured output."""
    config = _single_review_config()
    responses = [
        json.dumps({
            "summary": "Initial plan",
            "repo_analysis": {"languages": ["python"]},
            "subtasks": [{
                "id": "s1",
                "description": "Review code",
                "assigned_worker": "review",
                "context": {},
                "dependencies": [],
                "priority": 1,
            }],
            "global_context": {"repo_path": "/tmp/mock-repo"},
        }),
        "not valid worker output",
        _mock_worker_response("review"),
        _mock_judge_response(),
    ]
    counter = {"n": 0}

    def mock_query(*, prompt, options=None):
        idx = min(counter["n"], len(responses) - 1)
        counter["n"] += 1
        return _mock_query_generator(responses[idx])

    with patch("parallel_agents.agents.planner.query", new=mock_query):
        with patch("parallel_agents.agents.base.query", new=mock_query):
            with patch("parallel_agents.agents.judge.query", new=mock_query):
                pipeline = Pipeline(config)
                result = await pipeline.run("Review task", repo_path="/tmp/mock-repo")

    assert result.summary == "Analysis complete: 2 findings across 2 workers"
    assert counter["n"] == 4


@pytest.mark.asyncio
async def test_pipeline_suppresses_invalid_judge_patch():
    """Invalid patch output should be removed and annotated in metadata."""
    config = _single_review_config()
    responses = [
        json.dumps({
            "summary": "Initial plan",
            "repo_analysis": {"languages": ["python"]},
            "subtasks": [{
                "id": "s1",
                "description": "Review code",
                "assigned_worker": "review",
                "context": {},
                "dependencies": [],
                "priority": 1,
            }],
            "global_context": {"repo_path": "/tmp/mock-repo"},
        }),
        _mock_worker_response("review"),
        _mock_judge_invalid_patch_response(),
    ]
    counter = {"n": 0}

    def mock_query(*, prompt, options=None):
        idx = min(counter["n"], len(responses) - 1)
        counter["n"] += 1
        return _mock_query_generator(responses[idx])

    with patch("parallel_agents.agents.planner.query", new=mock_query):
        with patch("parallel_agents.agents.base.query", new=mock_query):
            with patch("parallel_agents.agents.judge.query", new=mock_query):
                pipeline = Pipeline(config)
                result = await pipeline.run("Review task", repo_path="/tmp/mock-repo")

    assert result.patch is None
    assert result.metadata["patch_validation"]["valid"] is False
    assert "invalid_patch" in result.metadata


@pytest.mark.asyncio
async def test_pipeline_github_issue_happy_path_injects_issue_context():
    """Fetched GitHub issue data should be included in planner input context."""
    config = _single_review_config()
    responses = [
        json.dumps({
            "summary": "Plan from GitHub issue",
            "repo_analysis": {"languages": ["python"]},
            "subtasks": [{
                "id": "s1",
                "description": "Review code",
                "assigned_worker": "review",
                "context": {},
                "dependencies": [],
                "priority": 1,
            }],
            "global_context": {"repo_path": "/tmp/mock-repo"},
        }),
        _mock_worker_response("review"),
        _mock_judge_response(),
    ]
    counter = {"n": 0}
    planner_prompts: list[str] = []

    def mock_planner_query(*, prompt, options=None):
        planner_prompts.append(prompt)
        idx = min(counter["n"], len(responses) - 1)
        counter["n"] += 1
        return _mock_query_generator(responses[idx])

    def mock_other_query(*, prompt, options=None):
        idx = min(counter["n"], len(responses) - 1)
        counter["n"] += 1
        return _mock_query_generator(responses[idx])

    fake_issue = GitHubIssue(
        number=42,
        title="Fix auth edge case",
        body="Repro: login fails on empty redirect",
        labels=["bug", "auth"],
        state="OPEN",
        url="https://github.com/org/repo/issues/42",
        comments=[{"author": "alice", "body": "This blocks release"}],
    )

    with patch("parallel_agents.pipeline.fetch_issue", new=AsyncMock(return_value=fake_issue)):
        with patch("parallel_agents.agents.planner.query", new=mock_planner_query):
            with patch("parallel_agents.agents.base.query", new=mock_other_query):
                with patch("parallel_agents.agents.judge.query", new=mock_other_query):
                    pipeline = Pipeline(config)
                    result = await pipeline.run(
                        "https://github.com/org/repo/issues/42",
                        repo_path="/tmp/mock-repo",
                    )

    assert result.summary == "Analysis complete: 2 findings across 2 workers"
    assert planner_prompts, "Planner query should have been called."
    planner_prompt = planner_prompts[0]
    assert "Issue title: Fix auth edge case" in planner_prompt
    assert "Issue body:" in planner_prompt
    assert "This blocks release" in planner_prompt
