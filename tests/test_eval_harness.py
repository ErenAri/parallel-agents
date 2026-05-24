"""Tests for evaluation harness metrics and serialization."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from parallel_agents.eval_harness import (
    EvaluationAnnotationUpdate,
    EvaluationAnnotations,
    EvaluationAggregate,
    EvaluationBreakdown,
    EvaluationResults,
    EvaluationRunRecord,
    apply_evaluation_annotations,
    compare_evaluation_results,
    compute_evaluation_breakdown,
    compute_evaluation_score,
    evaluate_score_gate,
    load_evaluation_dataset,
    summarize_evaluation_results,
    render_evaluation_report,
)


def test_load_evaluation_dataset_supports_list_shape(tmp_path):
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "id": "case-1",
                    "task": "Review auth module",
                    "repo_path": "./repo-a",
                    "baseline_human_minutes": 120,
                }
            ]
        ),
        encoding="utf-8",
    )

    dataset = load_evaluation_dataset(dataset_path)
    assert dataset.name == "default"
    assert len(dataset.cases) == 1
    assert dataset.cases[0].id == "case-1"
    assert dataset.cases[0].baseline_human_minutes == 120


def test_compute_evaluation_score_and_report():
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 5, 21, 11, 0, tzinfo=timezone.utc)

    results = EvaluationResults(
        dataset_name="benchmark-v1",
        dataset_path="/tmp/bench.json",
        baseline_acceptance_rate=0.5,
        baseline_regression_rate=0.1,
        runs=[
            EvaluationRunRecord(
                case_id="c1",
                task="Fix security issue",
                baseline_human_minutes=120,
                started_at=started,
                completed_at=ended,
                duration_seconds=1800,
                status="success",
                summary="done",
                total_tokens=10_000,
                total_cost_usd=0.15,
                patch_generated=True,
                annotations=EvaluationAnnotations(
                    reviewer_minutes=10,
                    accepted_without_major_edits=True,
                    introduced_regression=False,
                    findings_true_positives=3,
                    findings_false_positives=1,
                ),
            ),
            EvaluationRunRecord(
                case_id="c2",
                task="Refactor API",
                baseline_human_minutes=60,
                started_at=started,
                completed_at=ended,
                duration_seconds=4200,
                status="success",
                summary="done",
                total_tokens=7_500,
                total_cost_usd=0.11,
                patch_generated=False,
                annotations=EvaluationAnnotations(
                    reviewer_minutes=0,
                    accepted_without_major_edits=False,
                    introduced_regression=True,
                    findings_true_positives=1,
                    findings_false_positives=1,
                ),
            ),
        ],
    )

    score = compute_evaluation_score(results)
    assert score.case_count == 2
    assert score.completed_count == 2
    assert score.failed_count == 0
    assert score.speed_sample_size == 2
    assert score.acceptance_sample_size == 2
    assert score.regression_sample_size == 2
    assert score.finding_precision_sample_size == 6
    assert score.speed_gain_median == 0.25
    assert score.acceptance_rate == 0.5
    assert score.regression_rate == 0.5
    assert round(score.finding_precision or 0, 4) == 0.6667
    assert round(score.weighted_delivery_impact_score or 0, 4) == 0.02

    report = render_evaluation_report(results, score)
    assert "Evaluation Report" in report
    assert "Weighted Delivery Impact Score" in report
    assert "c1" in report and "c2" in report


def test_compute_evaluation_score_excludes_runtime_errors_from_speed():
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 5, 21, 10, 1, tzinfo=timezone.utc)

    results = EvaluationResults(
        dataset_name="runtime-error-only",
        dataset_path="/tmp/results.json",
        runs=[
            EvaluationRunRecord(
                case_id="err-1",
                task="task",
                baseline_human_minutes=30,
                started_at=started,
                completed_at=ended,
                duration_seconds=10,
                status="runtime_error",
                summary="Run failed",
            )
        ],
    )

    score = compute_evaluation_score(results)
    assert score.failed_count == 1
    assert score.completed_count == 0
    assert score.speed_sample_size == 0
    assert score.speed_gain_median is None


def test_compare_evaluation_results_and_gate():
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended_fast = datetime(2026, 5, 21, 10, 10, tzinfo=timezone.utc)
    ended_slow = datetime(2026, 5, 21, 10, 30, tzinfo=timezone.utc)

    baseline = EvaluationResults(
        dataset_name="bench",
        dataset_path="/tmp/base.json",
        baseline_acceptance_rate=0.5,
        baseline_regression_rate=0.1,
        runs=[
            EvaluationRunRecord(
                case_id="c1",
                task="task",
                baseline_human_minutes=60,
                started_at=started,
                completed_at=ended_fast,
                duration_seconds=600,
                status="success",
                summary="ok",
                total_cost_usd=0.30,
                annotations=EvaluationAnnotations(
                    accepted_without_major_edits=True,
                    introduced_regression=False,
                    findings_true_positives=3,
                    findings_false_positives=1,
                ),
            )
        ],
    )
    candidate = EvaluationResults(
        dataset_name="bench",
        dataset_path="/tmp/cand.json",
        baseline_acceptance_rate=0.5,
        baseline_regression_rate=0.1,
        runs=[
            EvaluationRunRecord(
                case_id="c1",
                task="task",
                baseline_human_minutes=60,
                started_at=started,
                completed_at=ended_slow,
                duration_seconds=1800,
                status="success",
                summary="ok",
                total_cost_usd=0.10,
                annotations=EvaluationAnnotations(
                    accepted_without_major_edits=False,
                    introduced_regression=True,
                    findings_true_positives=1,
                    findings_false_positives=2,
                ),
            )
        ],
    )

    comparison = compare_evaluation_results(
        baseline,
        candidate,
        baseline_results_path="/tmp/base.json",
        candidate_results_path="/tmp/cand.json",
    )
    assert round(comparison.total_cost_usd_delta, 4) == -0.2
    assert comparison.total_duration_seconds_delta == 1200
    assert comparison.acceptance_rate_delta == -1.0
    assert comparison.regression_rate_delta == 1.0

    score = compute_evaluation_score(candidate)
    aggregate = summarize_evaluation_results(candidate)
    gate = evaluate_score_gate(
        score,
        aggregate,
        max_regression_rate=0.3,
        min_acceptance_rate=0.5,
        min_finding_precision=0.5,
        max_total_cost_usd=1.0,
        max_total_duration_seconds=4000,
    )
    assert gate.passed is False
    assert len(gate.failed_rules) >= 2


def test_summarize_evaluation_results_counts_parse_and_worker_errors():
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 5, 21, 10, 1, tzinfo=timezone.utc)
    results = EvaluationResults(
        dataset_name="bench",
        dataset_path="/tmp/results.json",
        runs=[
            EvaluationRunRecord(
                case_id="p1",
                task="task",
                started_at=started,
                completed_at=ended,
                duration_seconds=10,
                status="parse_error",
                summary="failed to parse",
            ),
            EvaluationRunRecord(
                case_id="w1",
                task="task",
                started_at=started,
                completed_at=ended,
                duration_seconds=15,
                status="worker_error",
                summary="worker error",
            ),
            EvaluationRunRecord(
                case_id="r1",
                task="task",
                started_at=started,
                completed_at=ended,
                duration_seconds=20,
                status="runtime_error",
                summary="runtime error",
            ),
        ],
    )
    aggregate = summarize_evaluation_results(results)
    assert isinstance(aggregate, EvaluationAggregate)
    assert aggregate.case_count == 3
    assert aggregate.completed_count == 2
    assert aggregate.failed_count == 1
    assert aggregate.parse_error_count == 1
    assert aggregate.worker_error_count == 1


def test_apply_evaluation_annotations_updates_matching_case():
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 5, 21, 10, 1, tzinfo=timezone.utc)
    results = EvaluationResults(
        dataset_name="bench",
        dataset_path="/tmp/results.json",
        runs=[
            EvaluationRunRecord(
                case_id="c1",
                task="task",
                started_at=started,
                completed_at=ended,
                duration_seconds=10,
                status="success",
                summary="ok",
            )
        ],
    )
    updates = [
        EvaluationAnnotationUpdate(
            case_id="c1",
            reviewer_minutes=5,
            accepted_without_major_edits=True,
            introduced_regression=False,
            findings_true_positives=2,
            findings_false_positives=1,
        )
    ]

    annotated = apply_evaluation_annotations(results, updates)
    run = annotated.runs[0]
    assert run.annotations.reviewer_minutes == 5
    assert run.annotations.accepted_without_major_edits is True
    assert run.annotations.introduced_regression is False
    assert run.annotations.findings_true_positives == 2
    assert run.annotations.findings_false_positives == 1


def test_compute_evaluation_breakdown_groups_project_and_workflow():
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 5, 21, 10, 1, tzinfo=timezone.utc)
    results = EvaluationResults(
        dataset_name="bench",
        dataset_path="/tmp/results.json",
        runs=[
            EvaluationRunRecord(
                case_id="SEC-001",
                task="task",
                repo_path="/repo-a",
                started_at=started,
                completed_at=ended,
                duration_seconds=10,
                status="success",
                summary="ok",
                total_cost_usd=0.1,
            ),
            EvaluationRunRecord(
                case_id="TEST-001",
                task="task",
                repo_path="/repo-a",
                started_at=started,
                completed_at=ended,
                duration_seconds=20,
                status="runtime_error",
                summary="failed",
                total_cost_usd=0.2,
            ),
            EvaluationRunRecord(
                case_id="SEC-002",
                task="task",
                repo_path="/repo-b",
                started_at=started,
                completed_at=ended,
                duration_seconds=30,
                status="worker_error",
                summary="warn",
                total_cost_usd=0.3,
            ),
        ],
    )
    breakdown = compute_evaluation_breakdown(results)
    assert isinstance(breakdown, EvaluationBreakdown)
    assert len(breakdown.by_project) == 2
    assert len(breakdown.by_workflow) == 2
    sec_bucket = next(bucket for bucket in breakdown.by_workflow if bucket.key == "SEC")
    assert sec_bucket.case_count == 2
    assert round(sec_bucket.total_cost_usd, 4) == 0.4
