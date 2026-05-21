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

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from parallel_agents.company_artifacts import (
    append_company_artifact_event,
    list_company_artifact_paths,
    load_company_artifact,
    persist_company_artifact,
)
from parallel_agents.company_policy import (
    CompanyApplyPolicy,
    derive_policy_from_issue_plan,
    validate_issue_plan_against_policy,
)
from parallel_agents.company_workflows import (
    RoadmapPlan,
    build_github_workflow_templates,
    build_issue_plan_from_roadmap,
    build_release_readiness_report,
    build_roadmap,
    create_product_brief,
    recommend_tech_stack,
)
from parallel_agents.config import PipelineConfig
from parallel_agents.eval_harness import (
    compute_evaluation_score,
    load_evaluation_results,
)
from parallel_agents.mcp_tools import (
    run_single_worker,
    truncate_output,
)
from parallel_agents.pipeline import WORKER_REGISTRY, _load_workers
from parallel_agents.tools.github_tools import parse_repo_ref

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


@mcp.tool()
async def company_idea(
    idea: str,
    title: str = "",
    run_id: str = "",
    output_dir: str = ".parallel-agents-output",
) -> str:
    """Create a ProductBrief artifact from a plain-language idea."""
    try:
        brief = create_product_brief(idea=idea, title=title or None)
        payload = brief.model_dump(mode="json")
        if run_id:
            path = persist_company_artifact(output_dir, run_id, "brief", brief)
            payload["artifact_path"] = str(path)
            payload["run_id"] = run_id
        return json.dumps(payload, indent=2, default=str)
    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def company_stack(
    repo_path: str = "",
    focus: str = "AI software delivery workflow",
    run_id: str = "",
    output_dir: str = ".parallel-agents-output",
) -> str:
    """Recommend a technology stack based on repository signals."""
    try:
        resolved_repo = repo_path or os.getcwd()
        decision = recommend_tech_stack(repo_path=resolved_repo, product_focus=focus)
        payload = decision.model_dump(mode="json")
        if run_id:
            path = persist_company_artifact(output_dir, run_id, "stack", decision)
            payload["artifact_path"] = str(path)
            payload["run_id"] = run_id
        return json.dumps(payload, indent=2, default=str)
    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def company_roadmap(
    idea: str,
    horizon_weeks: int = 12,
    title: str = "",
    run_id: str = "",
    output_dir: str = ".parallel-agents-output",
) -> str:
    """Create a roadmap artifact from an idea."""
    try:
        if horizon_weeks <= 0:
            return json.dumps({
                "error": True,
                "message": "horizon_weeks must be greater than 0",
            })

        brief = create_product_brief(idea=idea, title=title or None)
        roadmap = build_roadmap(brief, horizon_weeks=horizon_weeks)
        payload = roadmap.model_dump(mode="json")
        if run_id:
            brief_path = persist_company_artifact(output_dir, run_id, "brief", brief)
            roadmap_path = persist_company_artifact(output_dir, run_id, "roadmap", roadmap)
            payload["brief_artifact_path"] = str(brief_path)
            payload["artifact_path"] = str(roadmap_path)
            payload["run_id"] = run_id
        return json.dumps(payload, indent=2, default=str)
    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def company_release_check(
    repo_path: str = "",
    run_id: str = "",
    output_dir: str = ".parallel-agents-output",
) -> str:
    """Run release-readiness checks for a repository."""
    try:
        resolved_repo = repo_path or os.getcwd()
        report = build_release_readiness_report(resolved_repo)
        payload = report.model_dump(mode="json")
        if run_id:
            path = persist_company_artifact(output_dir, run_id, "release-check", report)
            payload["artifact_path"] = str(path)
            payload["run_id"] = run_id
        return json.dumps(payload, indent=2, default=str)
    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def company_plan(
    roadmap_json: str,
    repo: str,
    labels: str = "planning,ai-agents",
    create_milestones: bool = True,
    run_id: str = "",
    output_dir: str = ".parallel-agents-output",
) -> str:
    """Create an approval-gated GitHub issue plan from a roadmap JSON payload."""
    try:
        if not run_id:
            return json.dumps({
                "error": True,
                "message": "run_id is required for approval-gated MCP planning",
            })
        parsed = parse_repo_ref(repo)
        if not parsed:
            return json.dumps({
                "error": True,
                "message": "repo must be owner/repo or a GitHub repository URL",
            })
        owner, repo_name = parsed
        roadmap = RoadmapPlan.model_validate(json.loads(roadmap_json))
        label_list = [label.strip() for label in labels.split(",") if label.strip()]
        issue_plan = build_issue_plan_from_roadmap(roadmap, default_labels=label_list)
        policy = derive_policy_from_issue_plan(f"{owner}/{repo_name}", issue_plan)

        from parallel_agents.main import _build_pending_company_issue_plan

        payload = _build_pending_company_issue_plan(
            owner=owner,
            repo=repo_name,
            issue_plan=issue_plan,
            create_milestones=create_milestones,
            apply_policy=policy,
        )
        payload["run_id"] = run_id
        path = persist_company_artifact(output_dir, run_id, "issue-plan", payload)
        payload["artifact_path"] = str(path)
        return json.dumps(payload, indent=2, default=str)
    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def company_approve(
    run_id: str,
    approver: str = "",
    approval_note: str = "",
    artifact: str = "issue-plan",
    output_dir: str = ".parallel-agents-output",
) -> str:
    """Approve a pending company issue plan artifact."""
    try:
        payload = load_company_artifact(output_dir, run_id, artifact)
        if not payload:
            return json.dumps({
                "error": True,
                "message": f"No artifact named '{artifact}' found for run {run_id}.",
            })
        approved_at = _utc_now()
        payload["approved"] = True
        payload["approval_status"] = "approved"
        payload["approved_at"] = approved_at
        payload["approved_by"] = approver or "mcp-approval"
        if approval_note:
            payload["approval_note"] = approval_note
        audit_path = append_company_artifact_event(
            output_dir,
            run_id,
            artifact,
            {
                "event": "approval_granted",
                "run_id": run_id,
                "artifact": artifact,
                "approved_by": payload["approved_by"],
                "approved_at": approved_at,
                "approval_note": approval_note or None,
            },
        )
        path = persist_company_artifact(output_dir, run_id, artifact, payload)
        payload["artifact_path"] = str(path)
        payload["approval_log_path"] = str(audit_path)
        return json.dumps(payload, indent=2, default=str)
    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def company_apply(
    run_id: str,
    artifact: str = "issue-plan",
    output_dir: str = ".parallel-agents-output",
) -> str:
    """Apply an approved company issue plan with policy validation before GitHub writes."""
    try:
        payload = load_company_artifact(output_dir, run_id, artifact)
        if not payload:
            return json.dumps({
                "error": True,
                "message": f"No artifact named '{artifact}' found for run {run_id}.",
            })
        if payload.get("requires_approval") and not payload.get("approved"):
            return json.dumps({
                "error": True,
                "message": "Plan is not approved yet.",
            })
        parsed = parse_repo_ref(str(payload.get("repo", "")))
        if not parsed:
            return json.dumps({
                "error": True,
                "message": "Artifact repo is invalid or missing.",
            })
        owner, repo_name = parsed
        issue_plan = payload.get("issue_plan") or []
        policy = derive_policy_from_issue_plan(f"{owner}/{repo_name}", issue_plan)
        if isinstance(payload.get("apply_policy"), dict):
            policy = CompanyApplyPolicy.model_validate(payload["apply_policy"])
        violations = validate_issue_plan_against_policy(
            repo_ref=f"{owner}/{repo_name}",
            issue_plan=issue_plan,
            policy=policy,
        )
        if violations:
            return json.dumps({
                "error": True,
                "message": "Apply policy check failed; no GitHub writes were attempted.",
                "violations": violations,
            }, indent=2)

        from parallel_agents.main import _execute_company_issue_plan

        result = await _execute_company_issue_plan(
            owner=owner,
            repo=repo_name,
            issue_plan=issue_plan,
            create_milestones=bool(payload.get("create_milestones", True)),
            dry_run=False,
        )
        result["approval_status"] = "applied"
        result["approved"] = bool(payload.get("approved"))
        path = persist_company_artifact(output_dir, run_id, artifact, result)
        result["artifact_path"] = str(path)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def company_artifacts(
    run_id: str,
    output_dir: str = ".parallel-agents-output",
) -> str:
    """List run-linked company artifacts."""
    try:
        artifacts = list_company_artifact_paths(output_dir, run_id)
        return json.dumps({
            "run_id": run_id,
            "output_dir": str(Path(output_dir).resolve()),
            "count": len(artifacts),
            "artifacts": artifacts,
        }, indent=2)
    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def company_templates(roadmap_json: str = "") -> str:
    """Generate recommended GitHub labels, milestones, and branch policy."""
    try:
        roadmap = RoadmapPlan.model_validate(json.loads(roadmap_json)) if roadmap_json else None
        payload = build_github_workflow_templates(roadmap)
        return json.dumps(payload, indent=2, default=str)
    except Exception as e:
        return _error_json(e)


@mcp.tool()
async def eval_score(results_path: str) -> str:
    """Compute evaluation scorecard metrics from an evaluation results JSON file."""
    try:
        results = load_evaluation_results(results_path)
        score = compute_evaluation_score(results)
        return json.dumps(score.model_dump(mode="json"), indent=2, default=str)
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


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def run_server() -> None:
    """Entry point for the MCP server. Starts in stdio transport mode."""
    mcp.run(transport="stdio")
