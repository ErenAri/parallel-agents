"""MCP server for parallel-agents.

Exposes parallel multi-agent code analysis as MCP tools that work with
any MCP-compatible AI coding tool: Claude Code, Codex CLI, Cursor,
Windsurf, Cline, Continue, Amazon Q, Zed, and more.

Usage:
    parallel-agents mcp          # start via CLI subcommand
    parallel-agents-mcp          # start via dedicated entry point

Tools exposed:
    review          — Full parallel analysis (all enabled workers)
    security_scan   — Security-focused analysis only
    test_analysis   — Test coverage gap analysis only
    perf_analysis   — Performance analysis only
    code_review     — Code quality review only
    analyze         — Custom worker selection
    list_workers    — Show available workers and config
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from parallel_agents.config import PipelineConfig
from parallel_agents.mcp_tools import (
    format_worker_result,
    run_single_worker,
    truncate_output,
)
from parallel_agents.pipeline import WORKER_REGISTRY, _load_workers

# Initialize the MCP server
mcp = FastMCP(
    "parallel-agents",
    instructions=(
        "Parallel multi-agent code analysis: security, testing, performance, "
        "architecture, devops, documentation, and code review. "
        "Fans out to specialist AI agents running concurrently, then synthesizes results."
    ),
)


@mcp.tool()
async def review(
    task: str,
    repo_path: str = "",
    workers: str = "",
    disable_workers: str = "",
) -> str:
    """Run a full parallel code analysis with all enabled specialist workers.

    Fans out to up to 8 specialist agents (security, test, perf, devops, arch,
    docs, code, review) running in parallel, then merges results via a judge.
    Returns unified findings, risk report, and recommendations.
    Takes 1-5 minutes depending on repo size and number of workers.

    Args:
        task: Description of the analysis task or what to focus on.
        repo_path: Path to the repository. Defaults to current working directory.
        workers: Comma-separated list of workers to enable (e.g. "security,test,perf").
                 Empty means all enabled workers.
        disable_workers: Comma-separated list of workers to disable.
    """
    try:
        from parallel_agents.pipeline import Pipeline

        config = PipelineConfig()
        resolved_repo = repo_path or os.getcwd()

        # Apply worker filters
        if workers:
            enabled = set(w.strip() for w in workers.split(","))
            for name in config.workers:
                config.workers[name].enabled = name in enabled

        if disable_workers:
            for name in disable_workers.split(","):
                name = name.strip()
                if name in config.workers:
                    config.workers[name].enabled = False

        pipeline = Pipeline(config)
        result = await pipeline.run(task, repo_path=resolved_repo)

        output = result.model_dump(mode="json")
        return truncate_output(output)

    except Exception as e:
        return json.dumps({
            "error": True,
            "error_type": type(e).__name__,
            "message": str(e),
            "suggestion": _error_suggestion(e),
        })


@mcp.tool()
async def security_scan(task: str, repo_path: str = "") -> str:
    """Run a security-focused analysis: OWASP Top 10, dependency vulnerabilities,
    secret scanning, authentication flaws, and injection risks.

    Bypasses the full pipeline for speed — runs the security specialist directly.
    Returns findings with severity levels and fix recommendations.

    Args:
        task: What to analyze (e.g. "Check for SQL injection and auth issues").
        repo_path: Path to the repository. Defaults to current working directory.
    """
    try:
        result = await run_single_worker("security", task, repo_path)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def test_analysis(task: str, repo_path: str = "") -> str:
    """Analyze test coverage gaps, missing test scenarios, and test quality.

    Returns findings about untested code paths and recommendations for
    improving the test suite with specific test cases to add.

    Args:
        task: What to analyze (e.g. "Find coverage gaps in the auth module").
        repo_path: Path to the repository. Defaults to current working directory.
    """
    try:
        result = await run_single_worker("test", task, repo_path)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def perf_analysis(task: str, repo_path: str = "") -> str:
    """Analyze performance: complexity hotspots, bottlenecks, memory issues,
    N+1 queries, and optimization opportunities.

    Args:
        task: What to analyze (e.g. "Find performance bottlenecks in the API layer").
        repo_path: Path to the repository. Defaults to current working directory.
    """
    try:
        result = await run_single_worker("perf", task, repo_path)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def code_review(task: str, repo_path: str = "") -> str:
    """Code quality review: style, best practices, SOLID principles, error
    handling, naming conventions, and maintainability.

    Args:
        task: What to review (e.g. "Review the new payment processing module").
        repo_path: Path to the repository. Defaults to current working directory.
    """
    try:
        result = await run_single_worker("review", task, repo_path)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def analyze(task: str, workers: str, repo_path: str = "") -> str:
    """Run analysis with a custom set of specialist workers.

    Available workers: security, test, perf, devops, arch, docs, code, review.
    For a single worker, runs directly (fast). For multiple workers, runs the
    full pipeline with parallel execution and result synthesis.

    Args:
        task: Description of the analysis task.
        workers: Comma-separated worker names (e.g. "security,test,perf").
        repo_path: Path to the repository. Defaults to current working directory.
    """
    try:
        worker_list = [w.strip() for w in workers.split(",") if w.strip()]

        if not worker_list:
            return json.dumps({
                "error": True,
                "message": "No workers specified. Available: security, test, perf, devops, arch, docs, code, review",
            })

        # Single worker: use direct path (faster, cheaper)
        if len(worker_list) == 1:
            result = await run_single_worker(worker_list[0], task, repo_path)
            return json.dumps(result, indent=2, default=str)

        # Multiple workers: use full pipeline with filter
        from parallel_agents.pipeline import Pipeline

        config = PipelineConfig()
        resolved_repo = repo_path or os.getcwd()

        enabled_set = set(worker_list)
        for name in config.workers:
            config.workers[name].enabled = name in enabled_set

        pipeline = Pipeline(config)
        result = await pipeline.run(task, repo_path=resolved_repo)

        output = result.model_dump(mode="json")
        return truncate_output(output)

    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def list_workers() -> str:
    """List all available specialist workers and their current configuration.

    Returns each worker's name, description, enabled status, model, and timeout.
    No API calls are made — this is a local config read.
    """
    try:
        _load_workers()
        config = PipelineConfig()

        worker_info = []
        for name, cls in sorted(WORKER_REGISTRY.items()):
            wc = config.workers.get(name)
            worker_info.append({
                "name": name,
                "description": getattr(cls, "description", ""),
                "enabled": wc.enabled if wc else True,
                "model": wc.model if wc else "sonnet",
                "timeout_seconds": wc.timeout_seconds if wc else 300,
            })

        return json.dumps({
            "workers": worker_info,
            "total": len(worker_info),
            "enabled_count": sum(1 for w in worker_info if w["enabled"]),
        }, indent=2)

    except Exception as e:
        return _error_json(e)


def _error_json(e: Exception) -> str:
    """Format an exception as a structured JSON error response."""
    return json.dumps({
        "error": True,
        "error_type": type(e).__name__,
        "message": str(e),
        "suggestion": _error_suggestion(e),
    })


def _error_suggestion(e: Exception) -> str:
    """Provide a helpful suggestion based on the error type."""
    error_msg = str(e).lower()
    if "api_key" in error_msg or "authentication" in error_msg or "unauthorized" in error_msg:
        return "Set ANTHROPIC_API_KEY as an environment variable or in a .env file."
    if "rate_limit" in error_msg or "overloaded" in error_msg:
        return "The API is rate-limited or overloaded. Wait a moment and try again."
    if "timeout" in error_msg:
        return "The operation timed out. Try a simpler task or increase the timeout in config."
    if "not found" in error_msg or "no such file" in error_msg:
        return "Check that the repo_path exists and is accessible."
    return "Check the error details above. Run 'parallel-agents workers' to verify configuration."


def run_server() -> None:
    """Entry point for the MCP server. Starts in stdio transport mode."""
    mcp.run(transport="stdio")
