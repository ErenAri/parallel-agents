"""Shared helpers for the MCP server layer.

Provides single-worker execution (bypassing planner/judge) and output
truncation to stay within MCP client token limits.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from parallel_agents.config import PipelineConfig, WorkerConfig
from parallel_agents.evidence_store import create_evidence_store
from parallel_agents.models import (
    FinalOutput,
    InputType,
    Subtask,
    TaskInput,
    TaskPlan,
    WorkerResult,
)
from parallel_agents.pipeline import WORKER_REGISTRY, _load_workers

# Severity ordering for truncation priority (lower = more important)
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


async def run_single_worker(
    worker_name: str,
    task: str,
    repo_path: str = "",
    config: PipelineConfig | None = None,
) -> dict[str, Any]:
    """Execute a single worker directly, bypassing planner/judge.

    Creates a synthetic TaskPlan and Subtask, then invokes the worker's
    execute_with_retry method. This is 3x faster and cheaper than the
    full pipeline for single-worker use cases.

    Returns the WorkerResult as a dict.
    """
    _load_workers()
    config = config or PipelineConfig()

    if worker_name not in WORKER_REGISTRY:
        available = ", ".join(sorted(WORKER_REGISTRY.keys()))
        return {
            "error": True,
            "message": f"Unknown worker '{worker_name}'. Available: {available}",
        }

    # Resolve repo path
    resolved_repo = repo_path or os.getcwd()

    # Create synthetic plan and subtask
    subtask = Subtask(
        id=f"mcp-direct-{worker_name}",
        description=task,
        assigned_worker=worker_name,
        context={"source": "mcp_direct"},
        priority=0,
    )

    plan = TaskPlan(
        summary=task,
        repo_analysis={"path": resolved_repo},
        subtasks=[subtask],
        global_context={"repo_path": resolved_repo},
    )

    # Get worker config
    worker_config = config.workers.get(worker_name, WorkerConfig())
    worker_cls = WORKER_REGISTRY[worker_name]
    worker = worker_cls(worker_config)

    # Create a temporary evidence store for this MCP call
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = create_evidence_store(tmp_dir, f"mcp-{worker_name}", "file")

        result = await worker.execute_with_retry(
            subtask,
            plan,
            max_retries=config.max_retries,
            retry_delay=config.retry_delay_seconds,
            timeout=worker_config.timeout_seconds,
        )

    return format_worker_result(result)


def format_worker_result(result: WorkerResult) -> dict[str, Any]:
    """Convert a WorkerResult to a clean dict for MCP output.

    Strips raw_output (often huge), keeps structured findings/recommendations,
    and adds summary statistics.
    """
    data = result.model_dump(mode="json")

    # Remove raw_output to save tokens
    data.pop("raw_output", None)

    # Add summary stats
    severity_counts: dict[str, int] = {}
    for finding in result.findings:
        sev = finding.severity.value if hasattr(finding.severity, "value") else str(finding.severity)
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    priority_counts: dict[str, int] = {}
    for rec in result.recommendations:
        pri = rec.priority.value if hasattr(rec.priority, "value") else str(rec.priority)
        priority_counts[pri] = priority_counts.get(pri, 0) + 1

    data["stats"] = {
        "total_findings": len(result.findings),
        "findings_by_severity": severity_counts,
        "total_recommendations": len(result.recommendations),
        "recommendations_by_priority": priority_counts,
    }

    return data


def truncate_output(output: dict[str, Any], max_chars: int = 32000) -> str:
    """Progressively truncate output to stay within MCP client token limits.

    Claude Code has a 10K token (~40K char) limit. We target 32K chars
    by default for safety margin. Applies progressive truncation:
    1. Drop raw_output and evidence fields
    2. Limit findings per worker to top 5 by severity
    3. Limit recommendations per worker to top 3
    4. Truncate patch to 1000 chars
    5. Fallback: summary + risk report only
    """
    # Phase 1: Drop raw_output and evidence
    _strip_verbose_fields(output)
    result = json.dumps(output, indent=2, default=str)
    if len(result) <= max_chars:
        return result

    # Phase 2: Limit findings and recommendations per worker
    if "worker_results" in output:
        for wr in output["worker_results"].values():
            if isinstance(wr, dict):
                _limit_findings(wr, max_per_worker=5)
                _limit_recommendations(wr, max_per_worker=3)
    if "risk_report" in output:
        output["risk_report"] = _sort_and_limit_findings(output["risk_report"], 10)

    result = json.dumps(output, indent=2, default=str)
    if len(result) <= max_chars:
        return result

    # Phase 3: Truncate patch and suggested_content
    if output.get("patch") and len(output["patch"]) > 1000:
        output["patch"] = output["patch"][:1000] + "\n... [truncated]"
    if "worker_results" in output:
        for wr in output["worker_results"].values():
            if isinstance(wr, dict):
                for rec in wr.get("recommendations", []):
                    if isinstance(rec, dict):
                        rec.pop("suggested_content", None)

    result = json.dumps(output, indent=2, default=str)
    if len(result) <= max_chars:
        return result

    # Phase 4: Collapse to summary only
    summary_output = {
        "summary": output.get("summary", ""),
        "risk_report": _sort_and_limit_findings(output.get("risk_report", []), 5),
        "worker_summary": {},
        "note": "Output was truncated to fit within token limits. Run with CLI for full results.",
    }
    if "worker_results" in output:
        for name, wr in output["worker_results"].items():
            if isinstance(wr, dict):
                summary_output["worker_summary"][name] = {
                    "status": wr.get("status", "unknown"),
                    "findings": len(wr.get("findings", [])),
                    "recommendations": len(wr.get("recommendations", [])),
                }
    if output.get("metadata", {}).get("run_id"):
        summary_output["run_id"] = output["metadata"]["run_id"]

    return json.dumps(summary_output, indent=2, default=str)


def _strip_verbose_fields(output: dict[str, Any]) -> None:
    """Remove raw_output and evidence from all nested structures."""
    output.pop("raw_output", None)
    if "worker_results" in output:
        for wr in output["worker_results"].values():
            if isinstance(wr, dict):
                wr.pop("raw_output", None)
                for finding in wr.get("findings", []):
                    if isinstance(finding, dict):
                        finding.pop("evidence", None)
    if "risk_report" in output:
        for finding in output["risk_report"]:
            if isinstance(finding, dict):
                finding.pop("evidence", None)


def _sort_and_limit_findings(findings: list, max_count: int) -> list:
    """Sort findings by severity and limit to max_count."""
    if not findings:
        return findings

    def _severity_key(f: Any) -> int:
        if isinstance(f, dict):
            sev = f.get("severity", "info")
        else:
            sev = getattr(f, "severity", "info")
            sev = sev.value if hasattr(sev, "value") else str(sev)
        return SEVERITY_ORDER.get(str(sev), 4)

    sorted_findings = sorted(findings, key=_severity_key)
    return sorted_findings[:max_count]


def _limit_findings(wr: dict, max_per_worker: int = 5) -> None:
    """Limit findings in a worker result dict."""
    if "findings" in wr:
        wr["findings"] = _sort_and_limit_findings(wr["findings"], max_per_worker)


def _limit_recommendations(wr: dict, max_per_worker: int = 3) -> None:
    """Limit recommendations in a worker result dict."""
    recs = wr.get("recommendations", [])
    if len(recs) > max_per_worker:
        # Sort by priority: must > should > could
        priority_order = {"must": 0, "should": 1, "could": 2}

        def _priority_key(r: Any) -> int:
            if isinstance(r, dict):
                pri = r.get("priority", "should")
            else:
                pri = getattr(r, "priority", "should")
                pri = pri.value if hasattr(pri, "value") else str(pri)
            return priority_order.get(str(pri), 1)

        wr["recommendations"] = sorted(recs, key=_priority_key)[:max_per_worker]
