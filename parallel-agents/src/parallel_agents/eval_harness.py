from __future__ import annotations

import random
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from parallel_agents.config import PipelineConfig
from parallel_agents.pipeline import Pipeline


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationCase(BaseModel):
    id: str
    task: str
    repo_path: str | None = None
    baseline_human_minutes: float | None = Field(default=None, ge=0.0)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class EvaluationDataset(BaseModel):
    name: str = "default"
    baseline_acceptance_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    baseline_regression_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    cases: list[EvaluationCase] = Field(default_factory=list)


class EvaluationAnnotations(BaseModel):
    reviewer_minutes: float | None = Field(default=None, ge=0.0)
    accepted_without_major_edits: bool | None = None
    introduced_regression: bool | None = None
    findings_true_positives: int | None = Field(default=None, ge=0)
    findings_false_positives: int | None = Field(default=None, ge=0)


class EvaluationRunRecord(BaseModel):
    case_id: str
    task: str
    repo_path: str | None = None
    baseline_human_minutes: float | None = None
    started_at: datetime
    completed_at: datetime
    duration_seconds: float = Field(ge=0.0)
    status: str
    run_id: str | None = None
    summary: str
    error_message: str | None = None
    patch_generated: bool = False
    risk_items: int = 0
    findings_count: int = 0
    recommendations_count: int = 0
    worker_error_count: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    annotations: EvaluationAnnotations = Field(default_factory=EvaluationAnnotations)


class EvaluationResults(BaseModel):
    generated_at: datetime = Field(default_factory=_utc_now)
    dataset_name: str
    dataset_path: str
    baseline_acceptance_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    baseline_regression_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    config: dict[str, Any] = Field(default_factory=dict)
    runs: list[EvaluationRunRecord] = Field(default_factory=list)


class EvaluationScore(BaseModel):
    generated_at: datetime = Field(default_factory=_utc_now)
    case_count: int
    completed_count: int
    failed_count: int
    speed_gain_median: float | None = None
    speed_gain_mean: float | None = None
    speed_gain_ci_low: float | None = None
    speed_gain_ci_high: float | None = None
    speed_sample_size: int = 0
    acceptance_rate: float | None = None
    acceptance_gain: float | None = None
    acceptance_sample_size: int = 0
    regression_rate: float | None = None
    regression_increase: float | None = None
    regression_sample_size: int = 0
    finding_precision: float | None = None
    finding_precision_sample_size: int = 0
    weighted_delivery_impact_score: float | None = None


def load_evaluation_dataset(path: str | Path) -> EvaluationDataset:
    source = Path(path)
    data = _read_json(source)
    if isinstance(data, list):
        return EvaluationDataset(cases=[EvaluationCase.model_validate(item) for item in data])
    return EvaluationDataset.model_validate(data)


def load_evaluation_results(path: str | Path) -> EvaluationResults:
    source = Path(path)
    data = _read_json(source)
    return EvaluationResults.model_validate(data)


def save_evaluation_results(path: str | Path, results: EvaluationResults) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(results.model_dump_json(indent=2), encoding="utf-8")


def save_evaluation_score(path: str | Path, score: EvaluationScore) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(score.model_dump_json(indent=2), encoding="utf-8")


async def run_evaluation(
    dataset: EvaluationDataset,
    *,
    dataset_path: str | Path,
    config: PipelineConfig,
    repo_root: str | Path | None = None,
    on_status: Callable[[str], None] | None = None,
) -> EvaluationResults:
    runs: list[EvaluationRunRecord] = []
    root = Path(repo_root).resolve() if repo_root else None
    total_cases = len(dataset.cases)

    def _status(message: str) -> None:
        if on_status:
            on_status(message)

    for index, case in enumerate(dataset.cases, start=1):
        resolved_repo = _resolve_repo_path(case.repo_path, root)
        _status(f"Case {index}/{total_cases} [{case.id}] starting...")

        started_at = _utc_now()
        try:
            # Instantiate per case so cost tracking and state are isolated.
            pipeline = Pipeline(config.model_copy(deep=True))
            result = await pipeline.run(case.task, repo_path=resolved_repo)
            completed_at = _utc_now()
            cost = result.metadata.get("cost", {})
            findings_count = sum(len(worker.findings) for worker in result.worker_results.values())
            recommendations_count = sum(
                len(worker.recommendations) for worker in result.worker_results.values()
            )
            worker_error_count = sum(
                1 for worker in result.worker_results.values() if worker.status == "error"
            )

            status = "success"
            if worker_error_count > 0:
                status = "worker_error"
            if _is_parse_failure_summary(result.summary):
                status = "parse_error"

            runs.append(
                EvaluationRunRecord(
                    case_id=case.id,
                    task=case.task,
                    repo_path=resolved_repo,
                    baseline_human_minutes=case.baseline_human_minutes,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_seconds=max(0.0, (completed_at - started_at).total_seconds()),
                    status=status,
                    run_id=result.metadata.get("run_id"),
                    summary=result.summary,
                    patch_generated=bool(result.patch),
                    risk_items=len(result.risk_report),
                    findings_count=findings_count,
                    recommendations_count=recommendations_count,
                    worker_error_count=worker_error_count,
                    total_tokens=int(cost.get("total_tokens", 0) or 0),
                    total_cost_usd=float(cost.get("total_cost_usd", 0.0) or 0.0),
                )
            )
            _status(
                f"Case {index}/{total_cases} [{case.id}] done "
                f"({status}, {findings_count} findings, ${float(cost.get('total_cost_usd', 0.0) or 0.0):.4f})."
            )
        except Exception as exc:
            completed_at = _utc_now()
            runs.append(
                EvaluationRunRecord(
                    case_id=case.id,
                    task=case.task,
                    repo_path=resolved_repo,
                    baseline_human_minutes=case.baseline_human_minutes,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_seconds=max(0.0, (completed_at - started_at).total_seconds()),
                    status="runtime_error",
                    summary="Run failed",
                    error_message=str(exc),
                )
            )
            _status(f"Case {index}/{total_cases} [{case.id}] failed: {exc}")

    return EvaluationResults(
        dataset_name=dataset.name,
        dataset_path=str(Path(dataset_path).resolve()),
        baseline_acceptance_rate=dataset.baseline_acceptance_rate,
        baseline_regression_rate=dataset.baseline_regression_rate,
        config=_config_snapshot(config),
        runs=runs,
    )


def compute_evaluation_score(results: EvaluationResults) -> EvaluationScore:
    speed_samples: list[float] = []
    accepted_total = 0
    accepted_true = 0
    regression_total = 0
    regression_true = 0
    tp_sum = 0
    fp_sum = 0

    completed_count = 0
    failed_count = 0

    for run in results.runs:
        if run.status == "runtime_error":
            failed_count += 1
        else:
            completed_count += 1

        if (
            run.status != "runtime_error"
            and run.baseline_human_minutes
            and run.baseline_human_minutes > 0
        ):
            reviewer_minutes = run.annotations.reviewer_minutes or 0.0
            agent_total_minutes = (run.duration_seconds / 60.0) + reviewer_minutes
            speed_gain = (run.baseline_human_minutes - agent_total_minutes) / run.baseline_human_minutes
            speed_samples.append(speed_gain)

        if run.annotations.accepted_without_major_edits is not None:
            accepted_total += 1
            if run.annotations.accepted_without_major_edits:
                accepted_true += 1

        if run.annotations.introduced_regression is not None:
            regression_total += 1
            if run.annotations.introduced_regression:
                regression_true += 1

        if (
            run.annotations.findings_true_positives is not None
            and run.annotations.findings_false_positives is not None
        ):
            tp_sum += run.annotations.findings_true_positives
            fp_sum += run.annotations.findings_false_positives

    speed_gain_median = statistics.median(speed_samples) if speed_samples else None
    speed_gain_mean = statistics.mean(speed_samples) if speed_samples else None
    speed_ci_low, speed_ci_high = _bootstrap_median_ci(speed_samples)

    acceptance_rate = (accepted_true / accepted_total) if accepted_total else None
    regression_rate = (regression_true / regression_total) if regression_total else None
    finding_precision = (tp_sum / (tp_sum + fp_sum)) if (tp_sum + fp_sum) > 0 else None

    acceptance_gain = (
        (acceptance_rate - results.baseline_acceptance_rate)
        if acceptance_rate is not None
        else None
    )
    regression_increase = (
        (regression_rate - results.baseline_regression_rate)
        if regression_rate is not None
        else None
    )

    weighted_delivery_impact_score = None
    if speed_gain_median is not None and acceptance_gain is not None and regression_increase is not None:
        weighted_delivery_impact_score = (
            (0.4 * speed_gain_median)
            + (0.4 * acceptance_gain)
            - (0.2 * regression_increase)
        )

    return EvaluationScore(
        case_count=len(results.runs),
        completed_count=completed_count,
        failed_count=failed_count,
        speed_gain_median=speed_gain_median,
        speed_gain_mean=speed_gain_mean,
        speed_gain_ci_low=speed_ci_low,
        speed_gain_ci_high=speed_ci_high,
        speed_sample_size=len(speed_samples),
        acceptance_rate=acceptance_rate,
        acceptance_gain=acceptance_gain,
        acceptance_sample_size=accepted_total,
        regression_rate=regression_rate,
        regression_increase=regression_increase,
        regression_sample_size=regression_total,
        finding_precision=finding_precision,
        finding_precision_sample_size=(tp_sum + fp_sum),
        weighted_delivery_impact_score=weighted_delivery_impact_score,
    )


def render_evaluation_report(results: EvaluationResults, score: EvaluationScore) -> str:
    lines: list[str] = []
    lines.append("# Evaluation Report")
    lines.append("")
    lines.append(f"- Generated at: {score.generated_at.isoformat()}")
    lines.append(f"- Dataset: `{results.dataset_name}`")
    lines.append(f"- Cases: {score.case_count} (completed: {score.completed_count}, failed: {score.failed_count})")
    lines.append("")
    lines.append("## Scorecard")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Speed gain (median) | {_fmt_pct(score.speed_gain_median)} |")
    lines.append(f"| Speed gain (mean) | {_fmt_pct(score.speed_gain_mean)} |")
    lines.append(
        f"| Speed gain 95% CI | {_fmt_pct(score.speed_gain_ci_low)} to {_fmt_pct(score.speed_gain_ci_high)} |"
    )
    lines.append(f"| Acceptance rate | {_fmt_pct(score.acceptance_rate)} |")
    lines.append(f"| Acceptance gain vs baseline | {_fmt_pct(score.acceptance_gain)} |")
    lines.append(f"| Regression rate | {_fmt_pct(score.regression_rate)} |")
    lines.append(f"| Regression increase vs baseline | {_fmt_pct(score.regression_increase)} |")
    lines.append(f"| Finding precision | {_fmt_pct(score.finding_precision)} |")
    lines.append(
        f"| Weighted Delivery Impact Score | {_fmt_pct(score.weighted_delivery_impact_score)} |"
    )
    lines.append("")
    lines.append("## Sample Sizes")
    lines.append("")
    lines.append(f"- Speed samples: {score.speed_sample_size}")
    lines.append(f"- Acceptance samples: {score.acceptance_sample_size}")
    lines.append(f"- Regression samples: {score.regression_sample_size}")
    lines.append(f"- Finding precision labeled findings: {score.finding_precision_sample_size}")
    lines.append("")
    lines.append("## Per-Case Results")
    lines.append("")
    lines.append("| Case | Status | Duration (s) | Tokens | Cost (USD) | Patch |")
    lines.append("|---|---|---:|---:|---:|---|")
    for run in results.runs:
        lines.append(
            "| "
            f"{run.case_id} | {run.status} | {run.duration_seconds:.1f} | "
            f"{run.total_tokens:,} | ${run.total_cost_usd:.4f} | "
            f"{'yes' if run.patch_generated else 'no'} |"
        )
    lines.append("")
    lines.append(
        "Note: acceptance/regression/precision metrics require manual annotation "
        "in each run's `annotations` fields."
    )
    lines.append("")
    return "\n".join(lines)


def _resolve_repo_path(case_repo_path: str | None, repo_root: Path | None) -> str | None:
    if case_repo_path:
        case_path = Path(case_repo_path)
        if case_path.is_absolute():
            return str(case_path)
        if repo_root:
            return str((repo_root / case_path).resolve())
        return str(case_path.resolve())
    if repo_root:
        return str(repo_root)
    return None


def _config_snapshot(config: PipelineConfig) -> dict[str, Any]:
    return {
        "planner_model": config.planner_model,
        "judge_model": config.judge_model,
        "permission_mode": config.permission_mode,
        "store_backend": config.store_backend,
        "max_parallel_workers": config.max_parallel_workers,
        "enabled_workers": [name for name, worker in config.workers.items() if worker.enabled],
    }


def _is_parse_failure_summary(summary: str) -> bool:
    lowered = summary.lower()
    return "failed to parse" in lowered or "parse error" in lowered


def _bootstrap_median_ci(samples: list[float], iterations: int = 1000) -> tuple[float | None, float | None]:
    if len(samples) < 2:
        return None, None
    rng = random.Random(42)
    medians: list[float] = []
    sample_size = len(samples)
    for _ in range(iterations):
        draw = [samples[rng.randrange(sample_size)] for _ in range(sample_size)]
        medians.append(statistics.median(draw))
    medians.sort()
    low_idx = int(0.025 * (iterations - 1))
    high_idx = int(0.975 * (iterations - 1))
    return medians[low_idx], medians[high_idx]


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def _read_json(path: Path) -> Any:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
