from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from parallel_agents.desktop.services import engine as engine_module
from parallel_agents.desktop.services.engine import EngineService
from parallel_agents.eval_harness import (
    EvaluationAggregate,
    EvaluationAnnotations,
    EvaluationBreakdown,
    EvaluationBreakdownBucket,
    EvaluationGateResult,
    EvaluationResults,
    EvaluationRunRecord,
    EvaluationScore,
)
from parallel_agents.models import FinalOutput, WorkerResult
from parallel_agents.project_office import office_dir


def test_run_pipeline_persists_final_output_and_audit(tmp_path, monkeypatch):
    status_messages: list[str] = []

    class FakePipeline:
        def __init__(self, config) -> None:
            self.config = config

        async def run(self, task: str, repo_path: str | None = None, on_status=None):
            assert task == "Run a full review"
            assert repo_path == str(tmp_path.resolve())
            if on_status is not None:
                on_status("Planning: fake planner step")
            return FinalOutput(
                summary="Synthetic final summary",
                worker_results={
                    "security": WorkerResult(
                        worker_name="security",
                        subtask_id="sec-1",
                        status="success",
                    ),
                    "review": WorkerResult(
                        worker_name="review",
                        subtask_id="rev-1",
                        status="warning",
                    ),
                },
                metadata={
                    "run_id": "run-test-001",
                    "cost": {
                        "total_tokens": 321,
                        "total_cost_usd": 1.25,
                    },
                },
            )

    monkeypatch.setattr(engine_module, "Pipeline", FakePipeline)

    service = EngineService()
    service.open_project(tmp_path)
    result = asyncio.run(
        service.run_pipeline("Run a full review", on_status=status_messages.append)
    )

    assert status_messages == ["Planning: fake planner step"]
    assert result.run_id == "run-test-001"
    assert result.summary == "Synthetic final summary"
    assert result.total_tokens == 321
    assert result.total_cost_usd == 1.25
    assert result.worker_statuses == {"security": "success", "review": "warning"}

    artifact_path = (
        office_dir(tmp_path) / "run-test-001" / "company" / "final-output.json"
    )
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["summary"] == "Synthetic final summary"
    assert payload["metadata"]["run_id"] == "run-test-001"

    audit_path = office_dir(tmp_path) / "audit" / "events.jsonl"
    assert audit_path.exists()
    lines = [line for line in audit_path.read_text(encoding="utf-8").splitlines() if line]
    assert lines, "expected at least one audit event"
    latest = json.loads(lines[-1])
    assert latest["run_id"] == "run-test-001"
    assert latest["event"] == "run.execute"


def test_run_pipeline_requires_run_id(tmp_path, monkeypatch):
    class FakePipeline:
        def __init__(self, config) -> None:
            self.config = config

        async def run(self, task: str, repo_path: str | None = None, on_status=None):
            return FinalOutput(summary="Missing run id", metadata={})

    monkeypatch.setattr(engine_module, "Pipeline", FakePipeline)

    service = EngineService()
    service.open_project(tmp_path)

    with pytest.raises(RuntimeError, match="run_id"):
        asyncio.run(service.run_pipeline("Run without id"))


def test_productivity_snapshot_reads_score_gate_and_breakdown(tmp_path):
    service = EngineService()
    service.open_project(tmp_path)

    metrics_dir = office_dir(tmp_path) / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    score = EvaluationScore(
        case_count=6,
        completed_count=6,
        failed_count=0,
        weighted_delivery_impact_score=0.18,
        acceptance_rate=0.82,
        regression_rate=0.05,
        finding_precision=0.75,
    )
    aggregate = EvaluationAggregate(
        case_count=6,
        completed_count=6,
        failed_count=0,
        total_cost_usd=2.4,
        total_duration_seconds=480.0,
    )
    gate = EvaluationGateResult(
        passed=False,
        failed_rules=["regression_rate above maximum (0.05 > 0.03)"],
        score=score,
        aggregate=aggregate,
    )
    breakdown = EvaluationBreakdown(
        by_project=[
            EvaluationBreakdownBucket(
                key="C:/repo-a",
                case_count=4,
                completed_count=4,
                failed_count=0,
                parse_error_count=0,
                worker_error_count=0,
                total_cost_usd=1.8,
                total_duration_seconds=320.0,
            )
        ],
        by_workflow=[
            EvaluationBreakdownBucket(
                key="RELEASE",
                case_count=3,
                completed_count=3,
                failed_count=0,
                parse_error_count=0,
                worker_error_count=0,
                total_cost_usd=1.1,
                total_duration_seconds=210.0,
            )
        ],
    )

    (metrics_dir / "eval-score.json").write_text(
        score.model_dump_json(indent=2), encoding="utf-8"
    )
    (metrics_dir / "eval-gate.json").write_text(
        gate.model_dump_json(indent=2), encoding="utf-8"
    )
    (metrics_dir / "eval-breakdown.json").write_text(
        breakdown.model_dump_json(indent=2), encoding="utf-8"
    )

    snapshot = service.productivity_snapshot()

    assert snapshot.score_path is not None
    assert snapshot.gate_path is not None
    assert snapshot.breakdown_path is not None
    assert snapshot.weighted_delivery_impact_score == pytest.approx(0.18)
    assert snapshot.acceptance_rate == pytest.approx(0.82)
    assert snapshot.regression_rate == pytest.approx(0.05)
    assert snapshot.finding_precision == pytest.approx(0.75)
    assert snapshot.case_count == 6
    assert snapshot.completed_count == 6
    assert snapshot.failed_count == 0
    assert snapshot.total_cost_usd == pytest.approx(2.4)
    assert snapshot.total_duration_seconds == pytest.approx(480.0)
    assert snapshot.gate_passed is False
    assert snapshot.gate_failed_rules
    assert snapshot.top_project == "C:/repo-a"
    assert snapshot.top_workflow == "RELEASE"


def test_productivity_snapshot_falls_back_to_results_when_score_missing(tmp_path):
    service = EngineService()
    service.open_project(tmp_path)

    eval_dir = tmp_path / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    results = EvaluationResults(
        dataset_name="local-dataset",
        dataset_path=str(eval_dir / "dataset.json"),
        runs=[
            EvaluationRunRecord(
                case_id="release-01",
                task="check release readiness",
                started_at=now,
                completed_at=now,
                duration_seconds=45.0,
                status="success",
                run_id="abc123",
                summary="ok",
                patch_generated=True,
                findings_count=2,
                recommendations_count=1,
                worker_error_count=0,
                total_tokens=1100,
                total_cost_usd=0.42,
                annotations=EvaluationAnnotations(
                    accepted_without_major_edits=True,
                    introduced_regression=False,
                    findings_true_positives=2,
                    findings_false_positives=0,
                ),
            )
        ],
    )
    (eval_dir / "results.json").write_text(
        results.model_dump_json(indent=2), encoding="utf-8"
    )

    snapshot = service.productivity_snapshot()

    assert snapshot.results_path is not None
    assert snapshot.score_path is None
    assert snapshot.case_count == 1
    assert snapshot.completed_count == 1
    assert snapshot.failed_count == 0
    assert snapshot.total_cost_usd == pytest.approx(0.42)
    assert snapshot.total_duration_seconds == pytest.approx(45.0)
    assert snapshot.notes
    assert any("Computed score from results artifact." in note for note in snapshot.notes)


def test_productivity_trend_reads_multiple_scores_and_gate(tmp_path):
    service = EngineService()
    service.open_project(tmp_path)

    metrics_dir = office_dir(tmp_path) / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    older_time = datetime(2026, 5, 21, 9, 0, 0, tzinfo=timezone.utc)
    newer_time = datetime(2026, 5, 22, 9, 0, 0, tzinfo=timezone.utc)

    older_score = EvaluationScore(
        generated_at=older_time,
        case_count=4,
        completed_count=4,
        failed_count=0,
        weighted_delivery_impact_score=0.10,
        acceptance_rate=0.70,
        regression_rate=0.08,
        finding_precision=0.60,
    )
    newer_score = EvaluationScore(
        generated_at=newer_time,
        case_count=5,
        completed_count=5,
        failed_count=0,
        weighted_delivery_impact_score=0.18,
        acceptance_rate=0.84,
        regression_rate=0.04,
        finding_precision=0.79,
    )
    gate = EvaluationGateResult(
        passed=True,
        failed_rules=[],
        score=newer_score,
        aggregate=EvaluationAggregate(
            case_count=5,
            completed_count=5,
            failed_count=0,
            total_cost_usd=1.2,
            total_duration_seconds=150.0,
        ),
    )
    breakdown = EvaluationBreakdown(
        by_project=[
            EvaluationBreakdownBucket(
                key="C:/repo-a",
                case_count=3,
                completed_count=3,
                failed_count=0,
                parse_error_count=0,
                worker_error_count=0,
                total_cost_usd=0.9,
                total_duration_seconds=110.0,
            )
        ],
        by_workflow=[
            EvaluationBreakdownBucket(
                key="RELEASE",
                case_count=2,
                completed_count=2,
                failed_count=0,
                parse_error_count=0,
                worker_error_count=0,
                total_cost_usd=0.6,
                total_duration_seconds=70.0,
            )
        ],
    )

    (metrics_dir / "2026-05-21-score.json").write_text(
        older_score.model_dump_json(indent=2), encoding="utf-8"
    )
    (metrics_dir / "2026-05-22-score.json").write_text(
        newer_score.model_dump_json(indent=2), encoding="utf-8"
    )
    (metrics_dir / "2026-05-22-gate.json").write_text(
        gate.model_dump_json(indent=2), encoding="utf-8"
    )
    (metrics_dir / "2026-05-22-breakdown.json").write_text(
        breakdown.model_dump_json(indent=2), encoding="utf-8"
    )

    trend = service.productivity_trend(limit=8)
    assert len(trend) == 2
    assert trend[0].generated_at == newer_time.isoformat()
    assert trend[0].gate_passed is True
    assert trend[0].total_cost_usd == pytest.approx(1.2)
    assert trend[0].total_duration_seconds == pytest.approx(150.0)
    assert "C:/repo-a" in trend[0].project_buckets
    assert trend[0].project_buckets["C:/repo-a"].case_count == 3
    assert "RELEASE" in trend[0].workflow_buckets
    assert trend[0].workflow_buckets["RELEASE"].total_cost_usd == pytest.approx(0.6)
    assert trend[1].generated_at == older_time.isoformat()
    assert trend[1].gate_passed is None


def test_compare_productivity_snapshots_returns_expected_deltas(tmp_path):
    service = EngineService()
    service.open_project(tmp_path)

    metrics_dir = office_dir(tmp_path) / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    baseline = EvaluationScore(
        generated_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
        case_count=5,
        completed_count=5,
        failed_count=0,
        weighted_delivery_impact_score=0.10,
        acceptance_rate=0.70,
        regression_rate=0.08,
        finding_precision=0.60,
    )
    candidate = EvaluationScore(
        generated_at=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
        case_count=6,
        completed_count=5,
        failed_count=1,
        weighted_delivery_impact_score=0.16,
        acceptance_rate=0.81,
        regression_rate=0.05,
        finding_precision=0.74,
    )

    baseline_path = metrics_dir / "baseline-score.json"
    candidate_path = metrics_dir / "candidate-score.json"
    baseline_path.write_text(baseline.model_dump_json(indent=2), encoding="utf-8")
    candidate_path.write_text(candidate.model_dump_json(indent=2), encoding="utf-8")

    (metrics_dir / "baseline-gate.json").write_text(
        EvaluationGateResult(
            passed=True,
            failed_rules=[],
            score=baseline,
            aggregate=EvaluationAggregate(
                case_count=5,
                completed_count=5,
                failed_count=0,
                total_cost_usd=1.0,
                total_duration_seconds=100.0,
            ),
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    (metrics_dir / "candidate-gate.json").write_text(
        EvaluationGateResult(
            passed=False,
            failed_rules=["failed_count above maximum (1 > 0)"],
            score=candidate,
            aggregate=EvaluationAggregate(
                case_count=6,
                completed_count=5,
                failed_count=1,
                total_cost_usd=1.5,
                total_duration_seconds=130.0,
            ),
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )

    comparison = service.compare_productivity_snapshots(
        baseline_score_path=baseline_path,
        candidate_score_path=candidate_path,
    )

    assert comparison.weighted_delivery_impact_delta == pytest.approx(0.06)
    assert comparison.acceptance_rate_delta == pytest.approx(0.11)
    assert comparison.regression_rate_delta == pytest.approx(-0.03)
    assert comparison.finding_precision_delta == pytest.approx(0.14)
    assert comparison.case_count_delta == 1
    assert comparison.completed_count_delta == 0
    assert comparison.failed_count_delta == 1
    assert comparison.total_cost_usd_delta == pytest.approx(0.5)
    assert comparison.total_duration_seconds_delta == pytest.approx(30.0)
    assert comparison.baseline_gate_passed is True
    assert comparison.candidate_gate_passed is False
