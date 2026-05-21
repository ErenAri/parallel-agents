"""Tests for evaluation harness metrics and serialization."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from parallel_agents.eval_harness import (
    EvaluationAnnotations,
    EvaluationResults,
    EvaluationRunRecord,
    compute_evaluation_score,
    load_evaluation_dataset,
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
