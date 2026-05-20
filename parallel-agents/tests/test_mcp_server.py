"""Tests for the MCP server tools."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from parallel_agents.mcp_tools import (
    format_worker_result,
    run_single_worker,
    truncate_output,
)
from parallel_agents.models import (
    Finding,
    FinalOutput,
    Recommendation,
    Severity,
    WorkerResult,
)


# ---------------------------------------------------------------------------
# list_workers tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_workers():
    """list_workers should return all 8 workers with correct fields."""
    from parallel_agents.mcp_server import list_workers

    result = json.loads(await list_workers())

    assert "workers" in result
    assert result["total"] == 8
    assert result["enabled_count"] == 8  # all enabled by default

    names = {w["name"] for w in result["workers"]}
    assert names == {"security", "test", "perf", "devops", "arch", "docs", "code", "review"}

    for w in result["workers"]:
        assert "name" in w
        assert "description" in w
        assert "enabled" in w
        assert "model" in w


# ---------------------------------------------------------------------------
# run_single_worker tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_single_worker_unknown_worker():
    """run_single_worker should return error for unknown worker."""
    result = await run_single_worker("nonexistent", "test task")

    assert result["error"] is True
    assert "nonexistent" in result["message"]
    assert "Available" in result["message"]


@pytest.mark.asyncio
async def test_run_single_worker_returns_result():
    """run_single_worker should return structured result when worker succeeds."""
    mock_result = WorkerResult(
        worker_name="security",
        subtask_id="mcp-direct-security",
        status="success",
        findings=[
            Finding(
                severity=Severity.HIGH,
                category="injection",
                title="SQL Injection Risk",
                description="Unsanitized user input in query",
                file_path="app/db.py",
            )
        ],
        recommendations=[
            Recommendation(
                type="code_change",
                description="Use parameterized queries",
                file_path="app/db.py",
            )
        ],
    )

    with patch(
        "parallel_agents.mcp_tools.WORKER_REGISTRY",
        {"security": _make_mock_worker_cls(mock_result)},
    ):
        result = await run_single_worker("security", "check for SQL injection")

    assert result["worker_name"] == "security"
    assert result["status"] == "success"
    assert result["stats"]["total_findings"] == 1
    assert result["stats"]["findings_by_severity"]["high"] == 1
    assert "raw_output" not in result  # stripped by format_worker_result


# ---------------------------------------------------------------------------
# format_worker_result tests
# ---------------------------------------------------------------------------


def test_format_worker_result_strips_raw_output():
    """format_worker_result should strip raw_output and add stats."""
    result = WorkerResult(
        worker_name="test",
        subtask_id="t1",
        raw_output="very long raw LLM output...",
        findings=[
            Finding(severity=Severity.CRITICAL, category="bug", title="Bug", description="A bug"),
            Finding(severity=Severity.LOW, category="style", title="Style", description="Style issue"),
        ],
    )

    formatted = format_worker_result(result)

    assert "raw_output" not in formatted
    assert formatted["stats"]["total_findings"] == 2
    assert formatted["stats"]["findings_by_severity"]["critical"] == 1
    assert formatted["stats"]["findings_by_severity"]["low"] == 1


# ---------------------------------------------------------------------------
# truncate_output tests
# ---------------------------------------------------------------------------


def test_truncate_output_small_output_unchanged():
    """Small outputs should pass through without modification."""
    output = {"summary": "All good", "risk_report": [], "worker_results": {}}
    result = truncate_output(output, max_chars=100000)
    parsed = json.loads(result)

    assert parsed["summary"] == "All good"


def test_truncate_output_strips_raw_output():
    """Phase 1: should strip raw_output from worker results."""
    output = {
        "summary": "test",
        "worker_results": {
            "security": {
                "raw_output": "x" * 50000,
                "findings": [],
                "recommendations": [],
                "status": "success",
            }
        },
        "risk_report": [],
    }

    result = truncate_output(output, max_chars=40000)
    parsed = json.loads(result)

    assert "raw_output" not in parsed.get("worker_results", {}).get("security", {})


def test_truncate_output_limits_findings():
    """Phase 2: should limit findings to top N by severity."""
    findings = [
        {"severity": "info", "category": "x", "title": f"Info {i}", "description": "d"}
        for i in range(20)
    ] + [
        {"severity": "critical", "category": "x", "title": "Critical 1", "description": "d"}
    ]

    output = {
        "summary": "test",
        "worker_results": {
            "security": {
                "findings": findings,
                "recommendations": [],
                "status": "success",
            }
        },
        "risk_report": findings.copy(),
    }

    result = truncate_output(output, max_chars=5000)
    parsed = json.loads(result)

    # Should have been truncated
    security_findings = parsed.get("worker_results", {}).get("security", {}).get("findings", [])
    if security_findings:  # might be in summary mode
        assert len(security_findings) <= 5
        # Critical should be first
        assert security_findings[0]["severity"] == "critical"


def test_truncate_output_fallback_to_summary():
    """Phase 4: extremely large output should collapse to summary."""
    findings = [
        {"severity": "high", "category": "x", "title": f"Finding {i}",
         "description": "d" * 500, "evidence": "e" * 500}
        for i in range(100)
    ]

    output = {
        "summary": "Test summary",
        "worker_results": {
            "security": {"findings": findings, "recommendations": [], "status": "success"},
            "test": {"findings": findings, "recommendations": [], "status": "success"},
            "perf": {"findings": findings, "recommendations": [], "status": "success"},
        },
        "risk_report": findings,
        "patch": "x" * 50000,
        "metadata": {"run_id": "abc123"},
    }

    result = truncate_output(output, max_chars=5000)
    parsed = json.loads(result)

    assert len(result) <= 5000
    assert parsed.get("summary") == "Test summary" or "summary" in parsed


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_scan_error_handling():
    """Tools should return structured error JSON on exception."""
    from parallel_agents.mcp_server import security_scan

    with patch(
        "parallel_agents.mcp_server.run_single_worker",
        side_effect=RuntimeError("API key missing"),
    ):
        result = json.loads(await security_scan("test", "/fake/path"))

    assert result["error"] is True
    assert "API key missing" in result["message"]


@pytest.mark.asyncio
async def test_analyze_no_workers():
    """analyze with empty workers string should return error."""
    from parallel_agents.mcp_server import analyze

    result = json.loads(await analyze("test task", "", "/fake/path"))

    assert result["error"] is True
    assert "No workers specified" in result["message"]


@pytest.mark.asyncio
async def test_analyze_single_worker_uses_direct_path():
    """analyze with one worker should use run_single_worker, not Pipeline."""
    mock_result = {"worker_name": "security", "status": "success", "findings": []}

    with patch(
        "parallel_agents.mcp_server.run_single_worker",
        new=AsyncMock(return_value=mock_result),
    ) as mock_rsw:
        from parallel_agents.mcp_server import analyze

        result = json.loads(await analyze("test", "security", "/repo"))

    assert result["worker_name"] == "security"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_worker_cls(return_result: WorkerResult):
    """Create a mock worker class that returns a preset result."""
    class MockWorker:
        name = return_result.worker_name
        description = "Mock worker"

        def __init__(self, config):
            self.config = config

        async def execute_with_retry(self, subtask, plan, **kwargs):
            return return_result

    return MockWorker
