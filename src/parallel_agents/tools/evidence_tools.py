"""MCP tool wrappers for evidence store access by agents.

These functions are designed to be registered as tools via the Claude Agent SDK's
@tool decorator when that API stabilizes. For now they serve as the interface
that workers call through the pipeline orchestrator.
"""

from __future__ import annotations

from typing import Any

from parallel_agents.evidence_store import EvidenceStore
from parallel_agents.models import Finding, Recommendation, Severity, WorkerResult


def store_finding(
    store: EvidenceStore,
    worker_name: str,
    finding: dict[str, Any],
) -> str:
    """Store a finding in the evidence store."""
    f = Finding(**finding)
    result = store.load_worker_result(worker_name)
    if result is None:
        result = WorkerResult(worker_name=worker_name, subtask_id="")
    result.findings.append(f)
    store.save_worker_result(result)
    return f"Finding stored: {f.title}"


def store_recommendation(
    store: EvidenceStore,
    worker_name: str,
    recommendation: dict[str, Any],
) -> str:
    """Store a recommendation in the evidence store."""
    r = Recommendation(**recommendation)
    result = store.load_worker_result(worker_name)
    if result is None:
        result = WorkerResult(worker_name=worker_name, subtask_id="")
    result.recommendations.append(r)
    store.save_worker_result(result)
    return f"Recommendation stored: {r.description[:80]}"


def read_findings(
    store: EvidenceStore,
    worker_name: str | None = None,
    min_severity: str | None = None,
) -> list[dict[str, Any]]:
    """Read findings from the evidence store, optionally filtered."""
    severity_order = {s: i for i, s in enumerate(Severity)}

    if worker_name:
        result = store.load_worker_result(worker_name)
        findings = result.findings if result else []
    else:
        all_results = store.load_all_worker_results()
        findings = []
        for r in all_results.values():
            findings.extend(r.findings)

    if min_severity:
        threshold = severity_order.get(Severity(min_severity), 4)
        findings = [f for f in findings if severity_order.get(f.severity, 4) <= threshold]

    return [f.model_dump() for f in findings]


def read_recommendations(
    store: EvidenceStore,
    worker_name: str | None = None,
) -> list[dict[str, Any]]:
    """Read recommendations from the evidence store."""
    if worker_name:
        result = store.load_worker_result(worker_name)
        recs = result.recommendations if result else []
    else:
        all_results = store.load_all_worker_results()
        recs = []
        for r in all_results.values():
            recs.extend(r.recommendations)

    return [r.model_dump() for r in recs]
