"""CLI integration tests for user-facing commands."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from click.testing import CliRunner

import parallel_agents.main as main_module
import parallel_agents.mcp_installer as mcp_installer_module
import parallel_agents.eval_harness as eval_harness_module
from parallel_agents.company_artifacts import (
    list_company_artifact_paths,
    load_company_artifact,
    load_company_artifact_events,
    persist_company_artifact,
)
from parallel_agents.eval_harness import (
    EvaluationAnnotations,
    EvaluationResults,
    EvaluationRunRecord,
)
from parallel_agents.evidence_store import create_evidence_store
from parallel_agents.models import FinalOutput, InputType, RunManifest, TaskInput, TaskStatus, WorkerResult


def _runner() -> CliRunner:
    return CliRunner()


def _sample_output(summary: str = "analysis complete", patch: str | None = None) -> FinalOutput:
    return FinalOutput(
        summary=summary,
        patch=patch,
        metadata={"run_id": "run-123"},
    )


def test_workers_command_lists_default_workers():
    runner = _runner()
    result = runner.invoke(main_module.cli, ["workers"])
    assert result.exit_code == 0
    assert "Available Workers" in result.output
    assert "security" in result.output
    assert "review" in result.output


def test_run_json_applies_cli_overrides(monkeypatch):
    captured: dict[str, object] = {}

    class FakePipeline:
        def __init__(self, config):
            captured["config"] = config

        async def run(self, task, repo_path=None, on_status=None):
            captured["task"] = task
            captured["repo_path"] = repo_path
            return _sample_output()

    monkeypatch.setattr(main_module, "Pipeline", FakePipeline)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        [
            "run",
            "review auth flow",
            "--repo",
            "./repo",
            "--workers",
            "security,code",
            "--disable-workers",
            "code",
            "--model",
            "haiku",
            "--permission-mode",
            "plan",
            "--output",
            "json",
            "--no-streaming",
        ],
    )

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["summary"] == "analysis complete"

    config = captured["config"]
    assert config.planner_model == "haiku"
    assert config.judge_model == "haiku"
    assert config.permission_mode == "plan"
    assert config.workers["security"].enabled is True
    assert config.workers["code"].enabled is False
    assert config.workers["review"].enabled is False
    assert all(worker.model == "haiku" for worker in config.workers.values())
    assert captured["task"] == "review auth flow"
    assert captured["repo_path"] == "./repo"


def test_run_patch_output_without_patch_exits_nonzero(monkeypatch):
    class FakePipeline:
        def __init__(self, config):
            self.config = config

        async def run(self, task, repo_path=None, on_status=None):
            return _sample_output(patch=None)

    monkeypatch.setattr(main_module, "Pipeline", FakePipeline)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["run", "task", "--output", "patch", "--no-streaming"],
    )
    assert result.exit_code == main_module.EXIT_NO_PATCH
    assert "No patch generated." in result.output


def test_run_apply_patch_requires_repo_path(monkeypatch):
    class FakePipeline:
        def __init__(self, config):
            self.config = config

        async def run(self, task, repo_path=None, on_status=None):
            return _sample_output(patch="--- a/f\n+++ b/f\n@@ -1 +1 @@\n-old\n+new\n")

    monkeypatch.setattr(main_module, "Pipeline", FakePipeline)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["run", "not-a-path-task", "--apply-patch", "--output", "json", "--no-streaming"],
    )
    assert result.exit_code == main_module.EXIT_RUNTIME_FAILURE
    assert "Cannot apply patch without repository path" in result.output


def test_run_apply_patch_requires_generated_patch(monkeypatch):
    class FakePipeline:
        def __init__(self, config):
            self.config = config

        async def run(self, task, repo_path=None, on_status=None):
            return _sample_output(patch=None)

    monkeypatch.setattr(main_module, "Pipeline", FakePipeline)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["run", "task", "--repo", "./repo", "--apply-patch", "--output", "json", "--no-streaming"],
    )
    assert result.exit_code == main_module.EXIT_NO_PATCH
    assert "No patch available to apply." in result.output


def test_run_apply_patch_success(monkeypatch):
    captured: dict[str, object] = {}

    class FakePipeline:
        def __init__(self, config):
            self.config = config

        async def run(self, task, repo_path=None, on_status=None):
            return _sample_output(
                patch="--- a/f\n+++ b/f\n@@ -1 +1 @@\n-old\n+new\n",
            )

    def fake_apply_unified_diff(repo_path: str, patch: str) -> tuple[bool, str]:
        captured["repo_path"] = repo_path
        captured["patch"] = patch
        return True, "Patch applied"

    monkeypatch.setattr(main_module, "Pipeline", FakePipeline)
    monkeypatch.setattr(main_module, "apply_unified_diff", fake_apply_unified_diff)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["run", "task", "--repo", "./repo", "--apply-patch", "--output", "json", "--no-streaming"],
    )

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["metadata"]["patch_apply"]["requested"] is True
    assert parsed["metadata"]["patch_apply"]["applied"] is True
    assert captured["repo_path"] == "./repo"


def test_run_returns_parse_exit_code(monkeypatch):
    class FakePipeline:
        def __init__(self, config):
            self.config = config

        async def run(self, task, repo_path=None, on_status=None):
            return _sample_output(summary="Failed to parse judge output")

    monkeypatch.setattr(main_module, "Pipeline", FakePipeline)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["run", "task", "--output", "json", "--no-streaming"],
    )
    assert result.exit_code == main_module.EXIT_PARSE_FAILURE


def test_run_returns_worker_failure_exit_code(monkeypatch):
    class FakePipeline:
        def __init__(self, config):
            self.config = config

        async def run(self, task, repo_path=None, on_status=None):
            return FinalOutput(
                summary="analysis complete",
                worker_results={
                    "review": WorkerResult(
                        worker_name="review",
                        subtask_id="s1",
                        status="error",
                    )
                },
            )

    monkeypatch.setattr(main_module, "Pipeline", FakePipeline)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["run", "task", "--output", "json", "--no-streaming"],
    )
    assert result.exit_code == main_module.EXIT_WORKER_FAILURE


def test_run_returns_auth_failure_exit_code(monkeypatch):
    class FakePipeline:
        def __init__(self, config):
            self.config = config

        async def run(self, task, repo_path=None, on_status=None):
            raise RuntimeError("Unauthorized: invalid API key")

    monkeypatch.setattr(main_module, "Pipeline", FakePipeline)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["run", "task", "--output", "json", "--no-streaming"],
    )
    assert result.exit_code == main_module.EXIT_AUTH_FAILURE
    assert "Run failed:" in result.output


def test_show_command_not_found_returns_exit_1(tmp_path):
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["show", "missing-run", "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "No run found with ID: missing-run" in result.output


def test_show_command_prints_manifest_and_output(tmp_path):
    run_id = "run-001"
    store = create_evidence_store(str(tmp_path), run_id, "file")
    manifest = RunManifest(
        run_id=run_id,
        input=TaskInput(raw_input="task", input_type=InputType.FREE_TEXT),
        status=TaskStatus.COMPLETED,
        workers_invoked=["security"],
        total_tokens=123,
        total_cost_usd=0.12,
    )
    store.save_manifest(manifest)
    store.save_final_output(_sample_output(summary="final summary"))

    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["show", run_id, "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Run ID: run-001" in result.output
    assert "final summary" in result.output


def test_history_command_file_backend_no_runs(tmp_path):
    output_dir = tmp_path / "does-not-exist"
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["history", "--output-dir", str(output_dir)],
    )
    assert result.exit_code == 0
    assert "No runs found." in result.output


def test_history_command_file_backend_lists_runs(tmp_path):
    run_id = "run-xyz"
    store = create_evidence_store(str(tmp_path), run_id, "file")
    store.save_manifest(
        RunManifest(
            run_id=run_id,
            input=TaskInput(raw_input="task", input_type=InputType.FREE_TEXT),
            status=TaskStatus.COMPLETED,
        )
    )
    store.save_final_output(_sample_output(summary="done"))

    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["history", "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert run_id in result.output
    assert "yes" in result.output


def test_mcp_install_command_calls_installer(monkeypatch):
    captured: dict[str, str] = {}

    def fake_install_for_target(target: str, scope: str = "project") -> str:
        captured["target"] = target
        captured["scope"] = scope
        return "OK mock installer result"

    monkeypatch.setattr(mcp_installer_module, "install_for_target", fake_install_for_target)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["mcp-install", "cursor", "--scope", "user"],
    )

    assert result.exit_code == 0
    assert captured["target"] == "cursor"
    assert captured["scope"] == "user"
    assert "OK mock installer result" in result.output


def test_eval_run_command_writes_results(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.json"
    output_path = tmp_path / "eval-results.json"
    repo_root = tmp_path / "repos"
    case_repo = repo_root / "repo-a"
    case_repo.mkdir(parents=True)
    dataset_path.write_text(
        json.dumps(
            {
                "name": "bench",
                "cases": [
                    {
                        "id": "c1",
                        "task": "Review auth module",
                        "repo_path": "repo-a",
                        "baseline_human_minutes": 90,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    class FakePipeline:
        def __init__(self, config):
            self.config = config

        async def run(self, task, repo_path=None, on_status=None):
            return FinalOutput(
                summary=f"done for {task}",
                patch="--- a/f\n+++ b/f\n@@ -1 +1 @@\n-old\n+new\n",
                worker_results={
                    "review": WorkerResult(worker_name="review", subtask_id="s1")
                },
                metadata={
                    "run_id": "run-eval-1",
                    "cost": {"total_tokens": 1234, "total_cost_usd": 0.0123},
                },
            )

    monkeypatch.setattr(main_module, "Pipeline", FakePipeline)
    monkeypatch.setattr(eval_harness_module, "Pipeline", FakePipeline)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        [
            "eval",
            "run",
            "--dataset",
            str(dataset_path),
            "--output",
            str(output_path),
            "--repo-root",
            str(repo_root),
        ],
    )
    assert result.exit_code == 0
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["dataset_name"] == "bench"
    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["case_id"] == "c1"
    assert payload["runs"][0]["run_id"] == "run-eval-1"
    assert payload["runs"][0]["patch_generated"] is True


def test_eval_score_command_json_output(tmp_path):
    results_path = tmp_path / "results.json"
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 5, 21, 10, 10, tzinfo=timezone.utc)
    data = EvaluationResults(
        dataset_name="bench",
        dataset_path=str(results_path),
        baseline_acceptance_rate=0.4,
        baseline_regression_rate=0.1,
        runs=[
            EvaluationRunRecord(
                case_id="c1",
                task="task",
                baseline_human_minutes=60,
                started_at=started,
                completed_at=ended,
                duration_seconds=600,
                status="success",
                summary="ok",
                annotations=EvaluationAnnotations(
                    accepted_without_major_edits=True,
                    introduced_regression=False,
                    findings_true_positives=2,
                    findings_false_positives=1,
                ),
            )
        ],
    )
    results_path.write_text(data.model_dump_json(indent=2), encoding="utf-8")

    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["eval", "score", "--results", str(results_path), "--json-output"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["case_count"] == 1
    assert payload["weighted_delivery_impact_score"] is not None


def test_eval_annotate_command_updates_results_in_place(tmp_path):
    results_path = tmp_path / "results.json"
    annotations_path = tmp_path / "annotations.json"
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 5, 21, 10, 10, tzinfo=timezone.utc)

    data = EvaluationResults(
        dataset_name="bench",
        dataset_path=str(results_path),
        runs=[
            EvaluationRunRecord(
                case_id="c1",
                task="task",
                baseline_human_minutes=60,
                started_at=started,
                completed_at=ended,
                duration_seconds=600,
                status="success",
                summary="ok",
            )
        ],
    )
    results_path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    annotations_path.write_text(
        json.dumps(
            [
                {
                    "case_id": "c1",
                    "accepted_without_major_edits": True,
                    "introduced_regression": False,
                    "findings_true_positives": 3,
                    "findings_false_positives": 1,
                }
            ]
        ),
        encoding="utf-8",
    )

    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        [
            "eval",
            "annotate",
            "--results",
            str(results_path),
            "--annotations",
            str(annotations_path),
            "--in-place",
        ],
    )
    assert result.exit_code == 0

    updated = json.loads(results_path.read_text(encoding="utf-8"))
    annotations_payload = updated["runs"][0]["annotations"]
    assert annotations_payload["accepted_without_major_edits"] is True
    assert annotations_payload["introduced_regression"] is False
    assert annotations_payload["findings_true_positives"] == 3


def test_eval_sync_pr_updates_acceptance_annotation(monkeypatch, tmp_path):
    results_path = tmp_path / "results.json"
    links_path = tmp_path / "pr-links.json"
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 5, 21, 10, 10, tzinfo=timezone.utc)

    data = EvaluationResults(
        dataset_name="bench",
        dataset_path=str(results_path),
        runs=[
            EvaluationRunRecord(
                case_id="c1",
                task="task",
                baseline_human_minutes=60,
                started_at=started,
                completed_at=ended,
                duration_seconds=600,
                status="success",
                summary="ok",
            )
        ],
    )
    results_path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    links_path.write_text(
        json.dumps(
            [
                {
                    "case_id": "c1",
                    "pr_url": "https://github.com/owner/repo/pull/10",
                }
            ]
        ),
        encoding="utf-8",
    )

    class FakePr:
        merged_at = "2026-05-22T12:00:00Z"
        review_decision = "APPROVED"
        changes_requested_count = 0
        approved_count = 1
        state = "MERGED"

    async def fake_fetch_pull_request(url: str):
        assert url.endswith("/pull/10")
        return FakePr()

    monkeypatch.setattr(main_module, "fetch_pull_request", fake_fetch_pull_request)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        [
            "eval",
            "sync-pr",
            "--results",
            str(results_path),
            "--links",
            str(links_path),
            "--in-place",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    annotations_payload = payload["runs"][0]["annotations"]
    assert annotations_payload["accepted_without_major_edits"] is True


def test_eval_sync_ci_updates_regression_annotation(tmp_path):
    results_path = tmp_path / "results.json"
    outcomes_path = tmp_path / "ci-outcomes.json"
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 5, 21, 10, 10, tzinfo=timezone.utc)

    data = EvaluationResults(
        dataset_name="bench",
        dataset_path=str(results_path),
        runs=[
            EvaluationRunRecord(
                case_id="c1",
                task="task",
                baseline_human_minutes=60,
                started_at=started,
                completed_at=ended,
                duration_seconds=600,
                status="success",
                summary="ok",
            )
        ],
    )
    results_path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    outcomes_path.write_text(
        json.dumps(
            [
                {
                    "case_id": "c1",
                    "ci_passed": False,
                    "source": "github-actions",
                }
            ]
        ),
        encoding="utf-8",
    )

    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        [
            "eval",
            "sync-ci",
            "--results",
            str(results_path),
            "--outcomes",
            str(outcomes_path),
            "--in-place",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    annotations_payload = payload["runs"][0]["annotations"]
    assert annotations_payload["introduced_regression"] is True


def test_eval_breakdown_command_json_output(tmp_path):
    results_path = tmp_path / "results.json"
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 5, 21, 10, 10, tzinfo=timezone.utc)
    data = EvaluationResults(
        dataset_name="bench",
        dataset_path=str(results_path),
        runs=[
            EvaluationRunRecord(
                case_id="SEC-001",
                task="task",
                repo_path="/repo-a",
                baseline_human_minutes=60,
                started_at=started,
                completed_at=ended,
                duration_seconds=600,
                status="success",
                summary="ok",
                total_cost_usd=0.15,
            )
        ],
    )
    results_path.write_text(data.model_dump_json(indent=2), encoding="utf-8")

    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["eval", "breakdown", "--results", str(results_path), "--json-output"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["by_project"][0]["key"] == "/repo-a"
    assert payload["by_workflow"][0]["key"] == "SEC"


def test_eval_compare_command_json_output(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended_short = datetime(2026, 5, 21, 10, 10, tzinfo=timezone.utc)
    ended_long = datetime(2026, 5, 21, 10, 20, tzinfo=timezone.utc)

    baseline = EvaluationResults(
        dataset_name="bench",
        dataset_path=str(baseline_path),
        runs=[
            EvaluationRunRecord(
                case_id="c1",
                task="task",
                baseline_human_minutes=60,
                started_at=started,
                completed_at=ended_short,
                duration_seconds=600,
                status="success",
                summary="ok",
                total_cost_usd=0.20,
                annotations=EvaluationAnnotations(
                    accepted_without_major_edits=True,
                    introduced_regression=False,
                    findings_true_positives=2,
                    findings_false_positives=1,
                ),
            )
        ],
    )
    candidate = EvaluationResults(
        dataset_name="bench",
        dataset_path=str(candidate_path),
        runs=[
            EvaluationRunRecord(
                case_id="c1",
                task="task",
                baseline_human_minutes=60,
                started_at=started,
                completed_at=ended_long,
                duration_seconds=1200,
                status="success",
                summary="ok",
                total_cost_usd=0.25,
                annotations=EvaluationAnnotations(
                    accepted_without_major_edits=False,
                    introduced_regression=True,
                    findings_true_positives=1,
                    findings_false_positives=2,
                ),
            )
        ],
    )
    baseline_path.write_text(baseline.model_dump_json(indent=2), encoding="utf-8")
    candidate_path.write_text(candidate.model_dump_json(indent=2), encoding="utf-8")

    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        [
            "eval",
            "compare",
            "--baseline-results",
            str(baseline_path),
            "--candidate-results",
            str(candidate_path),
            "--json-output",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["total_duration_seconds_delta"] == 600
    assert payload["failed_count_delta"] == 0


def test_eval_publish_writes_public_snapshot_and_report(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    output_json = tmp_path / "public.json"
    output_report = tmp_path / "public.md"
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended_short = datetime(2026, 5, 21, 10, 8, tzinfo=timezone.utc)
    ended_long = datetime(2026, 5, 21, 10, 12, tzinfo=timezone.utc)

    baseline = EvaluationResults(
        dataset_name="bench",
        dataset_path=str(baseline_path),
        runs=[
            EvaluationRunRecord(
                case_id="SEC-001",
                task="task",
                repo_path="/repo-a",
                baseline_human_minutes=60,
                started_at=started,
                completed_at=ended_long,
                duration_seconds=720,
                status="success",
                summary="ok",
                total_cost_usd=0.25,
                annotations=EvaluationAnnotations(
                    accepted_without_major_edits=True,
                    introduced_regression=False,
                    findings_true_positives=2,
                    findings_false_positives=1,
                ),
            )
        ],
    )
    candidate = EvaluationResults(
        dataset_name="bench",
        dataset_path=str(candidate_path),
        runs=[
            EvaluationRunRecord(
                case_id="SEC-001",
                task="task",
                repo_path="/repo-a",
                baseline_human_minutes=60,
                started_at=started,
                completed_at=ended_short,
                duration_seconds=480,
                status="success",
                summary="ok",
                total_cost_usd=0.20,
                annotations=EvaluationAnnotations(
                    accepted_without_major_edits=True,
                    introduced_regression=False,
                    findings_true_positives=3,
                    findings_false_positives=1,
                ),
            )
        ],
    )
    baseline_path.write_text(baseline.model_dump_json(indent=2), encoding="utf-8")
    candidate_path.write_text(candidate.model_dump_json(indent=2), encoding="utf-8")

    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        [
            "eval",
            "publish",
            "--results",
            str(candidate_path),
            "--baseline-results",
            str(baseline_path),
            "--label",
            "release-0.4.4-rc1",
            "--output-json",
            str(output_json),
            "--output-report",
            str(output_report),
            "--json-output",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["label"] == "release-0.4.4-rc1"
    assert "score" in payload
    assert "aggregate" in payload
    assert "comparison" in payload
    assert output_json.exists()
    assert output_report.exists()
    assert "Public Benchmark Report" in output_report.read_text(encoding="utf-8")


def test_eval_gate_command_fails_when_thresholds_not_met(tmp_path):
    results_path = tmp_path / "results.json"
    started = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 5, 21, 10, 20, tzinfo=timezone.utc)

    data = EvaluationResults(
        dataset_name="bench",
        dataset_path=str(results_path),
        runs=[
            EvaluationRunRecord(
                case_id="c1",
                task="task",
                baseline_human_minutes=60,
                started_at=started,
                completed_at=ended,
                duration_seconds=1200,
                status="success",
                summary="ok",
                annotations=EvaluationAnnotations(
                    accepted_without_major_edits=False,
                    introduced_regression=True,
                    findings_true_positives=1,
                    findings_false_positives=3,
                ),
            )
        ],
    )
    results_path.write_text(data.model_dump_json(indent=2), encoding="utf-8")

    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        [
            "eval",
            "gate",
            "--results",
            str(results_path),
            "--max-regression-rate",
            "0.1",
            "--min-acceptance-rate",
            "0.8",
        ],
    )
    assert result.exit_code == main_module.EXIT_RUNTIME_FAILURE
    assert "Gate failed" in result.output


def test_company_idea_command_json_output():
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["company", "idea", "Build a no-code release workflow", "--json-output"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["title"] == "Build A No-Code Release Workflow"
    assert payload["problem_statement"] == "Build a no-code release workflow"


def test_company_prfaq_command_from_brief(tmp_path):
    brief_path = tmp_path / "brief.json"
    runner = _runner()

    create_result = runner.invoke(
        main_module.cli,
        ["company", "idea", "Build company workflow automation", "--output", str(brief_path), "--json-output"],
    )
    assert create_result.exit_code == 0
    assert brief_path.exists()

    result = runner.invoke(
        main_module.cli,
        ["company", "prfaq", "--brief", str(brief_path), "--json-output"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "headline" in payload
    assert payload["customer_faq"]


def test_company_stack_command_json_output(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["company", "stack", "--repo", str(tmp_path), "--json-output"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["recommended_option"]
    assert "python" in payload["detected_signals"]


def test_company_roadmap_invalid_horizon_exits_runtime(tmp_path):
    brief_path = tmp_path / "brief.json"
    runner = _runner()
    create_result = runner.invoke(
        main_module.cli,
        ["company", "idea", "Build roadmap tooling", "--output", str(brief_path), "--json-output"],
    )
    assert create_result.exit_code == 0

    result = runner.invoke(
        main_module.cli,
        ["company", "roadmap", "--brief", str(brief_path), "--horizon-weeks", "0", "--json-output"],
    )
    assert result.exit_code == main_module.EXIT_RUNTIME_FAILURE
    assert "--horizon-weeks must be greater than 0." in result.output


def test_company_release_check_command_json_output(tmp_path):
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# changes\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_demo.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["company", "release-check", "--repo", str(tmp_path), "--json-output"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] in {"ready", "needs_attention"}
    assert payload["items"]


def test_company_sprint_command_from_roadmap(tmp_path):
    brief_path = tmp_path / "brief.json"
    roadmap_path = tmp_path / "roadmap.json"
    out_dir = tmp_path / "out"
    runner = _runner()

    runner.invoke(
        main_module.cli,
        ["company", "idea", "Build sprint planning", "--output", str(brief_path), "--json-output"],
    )
    runner.invoke(
        main_module.cli,
        ["company", "roadmap", "--brief", str(brief_path), "--output", str(roadmap_path), "--json-output"],
    )

    result = runner.invoke(
        main_module.cli,
        [
            "company",
            "sprint",
            "--roadmap",
            str(roadmap_path),
            "--milestone",
            "M1",
            "--run-id",
            "run-sprint",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["milestone"] == "M1"
    assert payload["items"]

    artifacts_result = runner.invoke(
        main_module.cli,
        ["company", "artifacts", "--run-id", "run-sprint", "--output-dir", str(out_dir), "--json-output"],
    )
    artifacts = json.loads(artifacts_result.output)
    assert "sprint" in artifacts["artifacts"]


def test_company_sprint_missing_milestone_fails(tmp_path):
    brief_path = tmp_path / "brief.json"
    roadmap_path = tmp_path / "roadmap.json"
    runner = _runner()

    runner.invoke(
        main_module.cli,
        ["company", "idea", "Build sprint planning", "--output", str(brief_path), "--json-output"],
    )
    runner.invoke(
        main_module.cli,
        ["company", "roadmap", "--brief", str(brief_path), "--output", str(roadmap_path), "--json-output"],
    )

    result = runner.invoke(
        main_module.cli,
        [
            "company",
            "sprint",
            "--roadmap",
            str(roadmap_path),
            "--milestone",
            "M99",
            "--json-output",
        ],
    )
    assert result.exit_code == main_module.EXIT_RUNTIME_FAILURE
    assert "No roadmap items" in result.output


def test_company_post_release_command_from_release_check(tmp_path):
    release_check_path = tmp_path / "release-check.json"
    metrics_path = tmp_path / "metrics.json"
    out_dir = tmp_path / "out"
    runner = _runner()

    release_result = runner.invoke(
        main_module.cli,
        ["company", "release-check", "--repo", str(tmp_path), "--output", str(release_check_path), "--json-output"],
    )
    assert release_result.exit_code == 0
    metrics_path.write_text('{"downloads": 3}', encoding="utf-8")

    result = runner.invoke(
        main_module.cli,
        [
            "company",
            "post-release",
            "--release-id",
            "v0.4.2",
            "--release-check",
            str(release_check_path),
            "--metrics",
            str(metrics_path),
            "--run-id",
            "run-post-release",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["release_id"] == "v0.4.2"
    assert payload["metrics"]["downloads"] == 3


def test_company_post_release_rejects_malformed_release_check(tmp_path):
    release_check_path = tmp_path / "bad-release-check.json"
    release_check_path.write_text('{"status": "ready"}', encoding="utf-8")
    runner = _runner()

    result = runner.invoke(
        main_module.cli,
        [
            "company",
            "post-release",
            "--release-id",
            "v0.4.2",
            "--release-check",
            str(release_check_path),
            "--json-output",
        ],
    )

    assert result.exit_code == main_module.EXIT_RUNTIME_FAILURE
    assert "Failed to load release check" in result.output


def test_company_templates_branch_name_and_pr_summary_commands(tmp_path):
    out_dir = tmp_path / "out"
    store = create_evidence_store(out_dir, "run-pr-summary", "file")
    store.save_final_output(
        FinalOutput(
            summary="Implemented product checkpoint.",
            risk_report=[],
            metadata={"tests_run": ["pytest -q"]},
        )
    )
    runner = _runner()

    templates_result = runner.invoke(
        main_module.cli,
        ["company", "templates", "--json-output"],
    )
    assert templates_result.exit_code == 0
    templates_payload = json.loads(templates_result.output)
    assert templates_payload["labels"]
    assert templates_payload["branch_policy"]["prefix"] == "pa"

    branch_result = runner.invoke(
        main_module.cli,
        [
            "company",
            "branch-name",
            "--issue",
            "RM-01",
            "--title",
            "Define Product And Workflow Artifacts",
            "--json-output",
        ],
    )
    assert branch_result.exit_code == 0
    branch_payload = json.loads(branch_result.output)
    assert branch_payload["branch"] == "pa/rm-01-define-product-and-workflow-artifacts"

    summary_result = runner.invoke(
        main_module.cli,
        [
            "company",
            "pr-summary",
            "--run-id",
            "run-pr-summary",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )
    assert summary_result.exit_code == 0
    summary_payload = json.loads(summary_result.output)
    assert "Implemented product checkpoint." in summary_payload["summary"]
    assert Path(summary_payload["output"]).exists()
    assert "pr-summary" in summary_payload["artifacts"]


def test_company_sync_labels_dry_run_and_live(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    runner = _runner()

    class _Label:
        def __init__(self, name: str, color: str, description: str):
            self.name = name
            self.color = color
            self.description = description

    async def fake_list_labels(owner: str, repo: str):
        assert owner == "owner"
        assert repo == "repo"
        return [_Label("planning", "ffffff", "old description")]

    create_calls: list[tuple[str, str, str]] = []
    update_calls: list[tuple[str, str, str]] = []

    async def fake_create_label(owner: str, repo: str, *, name: str, color: str, description: str = ""):
        create_calls.append((name, color, description))
        return _Label(name, color, description)

    async def fake_update_label(owner: str, repo: str, *, name: str, color: str, description: str = ""):
        update_calls.append((name, color, description))
        return _Label(name, color, description)

    monkeypatch.setattr(main_module, "list_labels", fake_list_labels)
    monkeypatch.setattr(main_module, "create_label", fake_create_label)
    monkeypatch.setattr(main_module, "update_label", fake_update_label)

    dry_result = runner.invoke(
        main_module.cli,
        [
            "company",
            "sync-labels",
            "--repo",
            "owner/repo",
            "--dry-run",
            "--run-id",
            "run-sync-labels",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )
    assert dry_result.exit_code == 0
    dry_payload = json.loads(dry_result.output)
    assert dry_payload["dry_run"] is True
    assert dry_payload["updated"] >= 1
    assert dry_payload["created"] >= 1
    assert not create_calls
    assert not update_calls
    assert "github-label-sync" in list_company_artifact_paths(out_dir, "run-sync-labels")

    live_result = runner.invoke(
        main_module.cli,
        [
            "company",
            "sync-labels",
            "--repo",
            "owner/repo",
            "--no-dry-run",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )
    assert live_result.exit_code == 0
    live_payload = json.loads(live_result.output)
    assert live_payload["dry_run"] is False
    assert len(create_calls) >= 1
    assert len(update_calls) >= 1


def test_company_sync_milestones_dry_run_and_live(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    roadmap_path = tmp_path / "roadmap.json"
    runner = _runner()

    runner.invoke(
        main_module.cli,
        ["company", "idea", "Build milestone sync", "--output", str(tmp_path / "brief.json"), "--json-output"],
    )
    runner.invoke(
        main_module.cli,
        [
            "company",
            "roadmap",
            "--brief",
            str(tmp_path / "brief.json"),
            "--output",
            str(roadmap_path),
            "--json-output",
        ],
    )

    class _Milestone:
        def __init__(self, title: str, state: str = "open"):
            self.title = title
            self.state = state

    async def fake_list_milestones(owner: str, repo: str, state: str = "all"):
        assert owner == "owner"
        assert repo == "repo"
        assert state == "all"
        return [_Milestone("M1")]

    create_calls: list[tuple[str, str]] = []

    async def fake_create_milestone(owner: str, repo: str, title: str, description: str = ""):
        create_calls.append((title, description))
        return _Milestone(title)

    monkeypatch.setattr(main_module, "list_milestones", fake_list_milestones)
    monkeypatch.setattr(main_module, "create_milestone", fake_create_milestone)

    dry_result = runner.invoke(
        main_module.cli,
        [
            "company",
            "sync-milestones",
            "--repo",
            "owner/repo",
            "--roadmap",
            str(roadmap_path),
            "--dry-run",
            "--run-id",
            "run-sync-milestones",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )
    assert dry_result.exit_code == 0
    dry_payload = json.loads(dry_result.output)
    assert dry_payload["dry_run"] is True
    assert dry_payload["created"] >= 1
    assert not create_calls
    assert "github-milestone-sync" in list_company_artifact_paths(out_dir, "run-sync-milestones")

    live_result = runner.invoke(
        main_module.cli,
        [
            "company",
            "sync-milestones",
            "--repo",
            "owner/repo",
            "--roadmap",
            str(roadmap_path),
            "--no-dry-run",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )
    assert live_result.exit_code == 0
    live_payload = json.loads(live_result.output)
    assert live_payload["dry_run"] is False
    assert len(create_calls) >= 1


def test_company_pr_link_updates_issue_plan_and_writes_audit(tmp_path):
    out_dir = tmp_path / "out"
    run_id = "run-link-1"
    runner = _runner()

    persist_company_artifact(
        out_dir,
        run_id,
        "issue-plan",
        {
            "run_id": run_id,
            "repo": "owner/repo",
            "issue_plan": [
                {
                    "source_item_id": "RM-01",
                    "title": "Define workflow",
                }
            ],
        },
    )

    result = runner.invoke(
        main_module.cli,
        [
            "company",
            "pr-link",
            "--run-id",
            run_id,
            "--pr-url",
            "https://github.com/owner/repo/pull/42",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["repo"] == "owner/repo"
    assert payload["number"] == 42
    assert payload["linked_artifact_found"] is True

    issue_plan = load_company_artifact(out_dir, run_id, "issue-plan")
    assert issue_plan is not None
    assert issue_plan["latest_pr_url"] == "https://github.com/owner/repo/pull/42"
    assert len(issue_plan["pr_links"]) == 1
    assert issue_plan["pr_links"][0]["number"] == 42

    pr_link_artifact = load_company_artifact(out_dir, run_id, "pr-link")
    assert pr_link_artifact is not None
    assert pr_link_artifact["pr_url"].endswith("/pull/42")

    events = load_company_artifact_events(out_dir, run_id, "pr-link")
    assert len(events) == 1
    assert events[0]["payload"]["event"] == "pr_linked"
    assert events[0]["payload"]["number"] == 42


def test_company_pr_create_persists_artifacts_and_links(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    run_id = "run-pr-create-1"
    runner = _runner()

    store = create_evidence_store(out_dir, run_id, "file")
    store.save_final_output(
        FinalOutput(
            summary="Complete feature implementation and tests.",
            risk_report=[],
            metadata={"tests_run": ["pytest -q"]},
        )
    )
    persist_company_artifact(
        out_dir,
        run_id,
        "issue-plan",
        {
            "run_id": run_id,
            "repo": "owner/repo",
            "issue_plan": [{"source_item_id": "RM-10", "title": "Ship release workflow"}],
        },
    )

    async def fake_create_pr(owner, repo, title, body, head, base="main", draft=False):
        assert owner == "owner"
        assert repo == "repo"
        assert head == "feature/run-pr-create-1"
        assert base == "main"
        assert draft is True
        assert "Complete feature implementation" in body
        return "https://github.com/owner/repo/pull/88"

    monkeypatch.setattr(main_module, "create_pr", fake_create_pr)

    result = runner.invoke(
        main_module.cli,
        [
            "company",
            "pr-create",
            "--run-id",
            run_id,
            "--head",
            "feature/run-pr-create-1",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["url"] == "https://github.com/owner/repo/pull/88"
    assert payload["repo"] == "owner/repo"
    assert payload["draft"] is True
    assert payload["pr_link"]["number"] == 88

    pr_create_artifact = load_company_artifact(out_dir, run_id, "pr-create")
    assert pr_create_artifact is not None
    assert pr_create_artifact["url"].endswith("/pull/88")

    issue_plan = load_company_artifact(out_dir, run_id, "issue-plan")
    assert issue_plan is not None
    assert issue_plan["latest_pr_url"].endswith("/pull/88")
    assert len(issue_plan["pr_links"]) == 1

    pr_create_events = load_company_artifact_events(out_dir, run_id, "pr-create")
    assert len(pr_create_events) == 1
    assert pr_create_events[0]["payload"]["event"] == "pr_created"


def test_company_pr_comment_posts_summary_and_risk(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    run_id = "run-pr-comment-1"
    runner = _runner()

    store = create_evidence_store(out_dir, run_id, "file")
    store.save_final_output(
        FinalOutput(
            summary="Implemented approval and release checks.",
            risk_report=[
                {
                    "severity": "high",
                    "category": "security",
                    "title": "Missing auth guard in admin endpoint",
                    "description": "Admin action endpoint is not protected.",
                    "file_path": "src/api/admin.py",
                }
            ],
        )
    )

    posted_bodies: list[str] = []

    async def fake_post_pr_comment(owner, repo, pr_number, body):
        assert owner == "owner"
        assert repo == "repo"
        assert pr_number == 99
        posted_bodies.append(body)
        return True

    monkeypatch.setattr(main_module, "post_pr_comment", fake_post_pr_comment)

    result = runner.invoke(
        main_module.cli,
        [
            "company",
            "pr-comment",
            "--run-id",
            run_id,
            "--pr-url",
            "https://github.com/owner/repo/pull/99",
            "--mode",
            "both",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["posted_all"] is True
    assert payload["posted_count"] == 2
    assert payload["attempted_count"] == 2
    assert len(posted_bodies) == 2
    assert "Parallel Agents Summary" in posted_bodies[0]
    assert "Parallel Agents Risk Report" in posted_bodies[1]

    pr_comment_artifact = load_company_artifact(out_dir, run_id, "pr-comment")
    assert pr_comment_artifact is not None
    assert pr_comment_artifact["posted_all"] is True

    pr_comment_events = load_company_artifact_events(out_dir, run_id, "pr-comment")
    assert len(pr_comment_events) == 1
    assert pr_comment_events[0]["payload"]["event"] == "pr_comments_posted"


def test_company_plan_dry_run_from_roadmap(tmp_path):
    brief_path = tmp_path / "brief.json"
    roadmap_path = tmp_path / "roadmap.json"
    runner = _runner()

    brief_result = runner.invoke(
        main_module.cli,
        ["company", "idea", "Build company planning pipeline", "--output", str(brief_path), "--json-output"],
    )
    assert brief_result.exit_code == 0

    roadmap_result = runner.invoke(
        main_module.cli,
        ["company", "roadmap", "--brief", str(brief_path), "--output", str(roadmap_path), "--json-output"],
    )
    assert roadmap_result.exit_code == 0
    assert roadmap_path.exists()

    result = runner.invoke(
        main_module.cli,
        [
            "company",
            "plan",
            "--roadmap",
            str(roadmap_path),
            "--repo",
            "owner/repo",
            "--dry-run",
            "--json-output",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["repo"] == "owner/repo"
    assert payload["dry_run"] is True
    assert payload["issues"]
    assert all(issue["status"] == "planned" for issue in payload["issues"])


def test_company_artifacts_list_from_run_id(tmp_path):
    brief_path = tmp_path / "brief.json"
    runner = _runner()

    result = runner.invoke(
        main_module.cli,
        [
            "company",
            "idea",
            "Build artifact linking",
            "--output",
            str(brief_path),
            "--run-id",
            "run-42",
            "--output-dir",
            str(tmp_path / "out"),
            "--json-output",
        ],
    )
    assert result.exit_code == 0

    list_result = runner.invoke(
        main_module.cli,
        [
            "company",
            "artifacts",
            "--run-id",
            "run-42",
            "--output-dir",
            str(tmp_path / "out"),
            "--json-output",
        ],
    )
    assert list_result.exit_code == 0
    payload = json.loads(list_result.output)
    assert payload["count"] >= 1
    assert "brief" in payload["artifacts"]


def test_company_plan_team_no_dry_run_requires_run_id(tmp_path):
    brief_path = tmp_path / "brief.json"
    roadmap_path = tmp_path / "roadmap.json"
    runner = _runner()

    runner.invoke(
        main_module.cli,
        ["company", "idea", "Build gated planning", "--output", str(brief_path), "--json-output"],
    )
    runner.invoke(
        main_module.cli,
        ["company", "roadmap", "--brief", str(brief_path), "--output", str(roadmap_path), "--json-output"],
    )

    result = runner.invoke(
        main_module.cli,
        [
            "company",
            "plan",
            "--roadmap",
            str(roadmap_path),
            "--repo",
            "owner/repo",
            "--no-dry-run",
            "--permission-profile",
            "team",
            "--json-output",
        ],
    )
    assert result.exit_code == main_module.EXIT_RUNTIME_FAILURE
    assert "requires --run-id" in result.output


def test_company_plan_team_no_dry_run_creates_pending(tmp_path):
    brief_path = tmp_path / "brief.json"
    roadmap_path = tmp_path / "roadmap.json"
    runner = _runner()

    runner.invoke(
        main_module.cli,
        ["company", "idea", "Build gated planning", "--output", str(brief_path), "--json-output"],
    )
    runner.invoke(
        main_module.cli,
        ["company", "roadmap", "--brief", str(brief_path), "--output", str(roadmap_path), "--json-output"],
    )

    result = runner.invoke(
        main_module.cli,
        [
            "company",
            "plan",
            "--roadmap",
            str(roadmap_path),
            "--repo",
            "owner/repo",
            "--no-dry-run",
            "--permission-profile",
            "team",
            "--run-id",
            "run-team-1",
            "--output-dir",
            str(tmp_path / "out"),
            "--json-output",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["requires_approval"] is True
    assert payload["approved"] is False
    assert payload["approval_status"] == "pending"
    assert payload["apply_policy"]["repo_allowlist"] == ["owner/repo"]


def test_company_approve_then_apply_flow(tmp_path, monkeypatch):
    brief_path = tmp_path / "brief.json"
    roadmap_path = tmp_path / "roadmap.json"
    out_dir = tmp_path / "out"
    runner = _runner()

    runner.invoke(
        main_module.cli,
        ["company", "idea", "Build gated planning", "--output", str(brief_path), "--json-output"],
    )
    runner.invoke(
        main_module.cli,
        ["company", "roadmap", "--brief", str(brief_path), "--output", str(roadmap_path), "--json-output"],
    )
    runner.invoke(
        main_module.cli,
        [
            "company",
            "plan",
            "--roadmap",
            str(roadmap_path),
            "--repo",
            "owner/repo",
            "--no-dry-run",
            "--permission-profile",
            "team",
            "--run-id",
            "run-team-2",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )

    approve_result = runner.invoke(
        main_module.cli,
        [
            "company",
            "approve",
            "--run-id",
            "run-team-2",
            "--output-dir",
            str(out_dir),
            "--approver",
            "qa-lead",
            "--approval-note",
            "Approved after scope review",
            "--json-output",
        ],
    )
    assert approve_result.exit_code == 0
    approved_payload = json.loads(approve_result.output)
    assert approved_payload["approved"] is True
    assert approved_payload["approved_by"] == "qa-lead"
    assert approved_payload["approval_note"] == "Approved after scope review"
    assert "approval_log_path" in approved_payload

    events = load_company_artifact_events(out_dir, "run-team-2", "issue-plan")
    assert len(events) == 1
    assert events[0]["payload"]["approval_note"] == "Approved after scope review"

    async def fake_execute_company_issue_plan(**kwargs):
        issue_plan = kwargs["issue_plan"]
        return {
            "repo": "owner/repo",
            "dry_run": False,
            "milestones": [],
            "issues": [
                {
                    "source_item_id": issue_plan[0]["source_item_id"],
                    "title": issue_plan[0]["title"],
                    "milestone": issue_plan[0]["milestone"],
                    "labels": issue_plan[0]["labels"],
                    "created": True,
                    "url": "https://github.com/owner/repo/issues/1",
                    "status": "created",
                }
            ],
            "issue_plan": issue_plan,
            "create_milestones": kwargs["create_milestones"],
        }

    monkeypatch.setattr(main_module, "_execute_company_issue_plan", fake_execute_company_issue_plan)

    apply_result = runner.invoke(
        main_module.cli,
        [
            "company",
            "apply",
            "--run-id",
            "run-team-2",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )
    assert apply_result.exit_code == 0
    applied_payload = json.loads(apply_result.output)
    assert applied_payload["approval_status"] == "applied"
    assert applied_payload["approved"] is True
    assert applied_payload["issues"][0]["created"] is True
    assert applied_payload["apply_policy_source"] == "artifact"


def test_company_apply_fails_when_unapproved(tmp_path):
    brief_path = tmp_path / "brief.json"
    roadmap_path = tmp_path / "roadmap.json"
    out_dir = tmp_path / "out"
    runner = _runner()

    runner.invoke(
        main_module.cli,
        ["company", "idea", "Build gated planning", "--output", str(brief_path), "--json-output"],
    )
    runner.invoke(
        main_module.cli,
        ["company", "roadmap", "--brief", str(brief_path), "--output", str(roadmap_path), "--json-output"],
    )
    runner.invoke(
        main_module.cli,
        [
            "company",
            "plan",
            "--roadmap",
            str(roadmap_path),
            "--repo",
            "owner/repo",
            "--no-dry-run",
            "--permission-profile",
            "team",
            "--run-id",
            "run-team-3",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )

    apply_result = runner.invoke(
        main_module.cli,
        [
            "company",
            "apply",
            "--run-id",
            "run-team-3",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )
    assert apply_result.exit_code == main_module.EXIT_RUNTIME_FAILURE
    assert "not approved yet" in apply_result.output


def test_company_apply_fails_policy_check_before_writes(tmp_path, monkeypatch):
    brief_path = tmp_path / "brief.json"
    roadmap_path = tmp_path / "roadmap.json"
    out_dir = tmp_path / "out"
    policy_path = tmp_path / "apply-policy.json"
    runner = _runner()

    runner.invoke(
        main_module.cli,
        ["company", "idea", "Build gated planning", "--output", str(brief_path), "--json-output"],
    )
    runner.invoke(
        main_module.cli,
        ["company", "roadmap", "--brief", str(brief_path), "--output", str(roadmap_path), "--json-output"],
    )
    runner.invoke(
        main_module.cli,
        [
            "company",
            "plan",
            "--roadmap",
            str(roadmap_path),
            "--repo",
            "owner/repo",
            "--no-dry-run",
            "--permission-profile",
            "team",
            "--run-id",
            "run-team-policy",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )
    runner.invoke(
        main_module.cli,
        [
            "company",
            "approve",
            "--run-id",
            "run-team-policy",
            "--output-dir",
            str(out_dir),
            "--json-output",
        ],
    )

    policy_path.write_text(
        json.dumps(
            {
                "repo_allowlist": ["owner/repo"],
                "label_allowlist": ["planning"],
                "milestone_allowlist": ["M1"],
            }
        ),
        encoding="utf-8",
    )

    async def should_not_run(**kwargs):
        raise AssertionError("GitHub writes should not be reached when policy fails")

    monkeypatch.setattr(main_module, "_execute_company_issue_plan", should_not_run)

    apply_result = runner.invoke(
        main_module.cli,
        [
            "company",
            "apply",
            "--run-id",
            "run-team-policy",
            "--output-dir",
            str(out_dir),
            "--policy-file",
            str(policy_path),
            "--json-output",
        ],
    )
    assert apply_result.exit_code == main_module.EXIT_RUNTIME_FAILURE
    assert "policy check failed" in apply_result.output.lower()


def test_gateway_start_uses_localhost_default(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_run_gateway_server(
        *,
        host,
        port,
        output_dir,
        api_key,
        jwt_secret,
        jwt_issuer,
        jwt_audience,
        allow_remote_write_tools,
        slack_signing_secret,
        slack_allow_unsigned,
    ):
        captured["host"] = host
        captured["port"] = port
        captured["output_dir"] = output_dir
        captured["api_key"] = api_key
        captured["jwt_secret"] = jwt_secret
        captured["jwt_issuer"] = jwt_issuer
        captured["jwt_audience"] = jwt_audience
        captured["allow_remote_write_tools"] = allow_remote_write_tools
        captured["slack_signing_secret"] = slack_signing_secret
        captured["slack_allow_unsigned"] = slack_allow_unsigned

    import parallel_agents.gateway as gateway_module

    monkeypatch.setattr(gateway_module, "run_gateway_server", fake_run_gateway_server)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["gateway", "start", "--output-dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8733
    assert captured["output_dir"] == str(tmp_path)
    assert captured["api_key"] is None
    assert captured["jwt_secret"] is None
    assert captured["jwt_issuer"] is None
    assert captured["jwt_audience"] is None
    assert captured["allow_remote_write_tools"] is False
    assert captured["slack_signing_secret"] is None
    assert captured["slack_allow_unsigned"] is False


def test_gateway_start_passes_api_key(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_run_gateway_server(
        *,
        host,
        port,
        output_dir,
        api_key,
        jwt_secret,
        jwt_issuer,
        jwt_audience,
        allow_remote_write_tools,
        slack_signing_secret,
        slack_allow_unsigned,
    ):
        captured["host"] = host
        captured["port"] = port
        captured["output_dir"] = output_dir
        captured["api_key"] = api_key
        captured["jwt_secret"] = jwt_secret
        captured["jwt_issuer"] = jwt_issuer
        captured["jwt_audience"] = jwt_audience
        captured["allow_remote_write_tools"] = allow_remote_write_tools
        captured["slack_signing_secret"] = slack_signing_secret
        captured["slack_allow_unsigned"] = slack_allow_unsigned

    import parallel_agents.gateway as gateway_module

    monkeypatch.setattr(gateway_module, "run_gateway_server", fake_run_gateway_server)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["gateway", "start", "--output-dir", str(tmp_path), "--api-key", "secret-token"],
    )

    assert result.exit_code == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8733
    assert captured["output_dir"] == str(tmp_path)
    assert captured["api_key"] == "secret-token"
    assert captured["jwt_secret"] is None
    assert captured["allow_remote_write_tools"] is False


def test_gateway_start_passes_jwt_options(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_run_gateway_server(
        *,
        host,
        port,
        output_dir,
        api_key,
        jwt_secret,
        jwt_issuer,
        jwt_audience,
        allow_remote_write_tools,
        slack_signing_secret,
        slack_allow_unsigned,
    ):
        captured["host"] = host
        captured["port"] = port
        captured["output_dir"] = output_dir
        captured["api_key"] = api_key
        captured["jwt_secret"] = jwt_secret
        captured["jwt_issuer"] = jwt_issuer
        captured["jwt_audience"] = jwt_audience
        captured["allow_remote_write_tools"] = allow_remote_write_tools
        captured["slack_signing_secret"] = slack_signing_secret
        captured["slack_allow_unsigned"] = slack_allow_unsigned

    import parallel_agents.gateway as gateway_module

    monkeypatch.setattr(gateway_module, "run_gateway_server", fake_run_gateway_server)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        [
            "gateway",
            "start",
            "--output-dir",
            str(tmp_path),
            "--jwt-secret",
            "secret",
            "--jwt-issuer",
            "issuer",
            "--jwt-audience",
            "aud",
        ],
    )

    assert result.exit_code == 0
    assert captured["jwt_secret"] == "secret"
    assert captured["jwt_issuer"] == "issuer"
    assert captured["jwt_audience"] == "aud"
    assert captured["allow_remote_write_tools"] is False


def test_gateway_start_passes_remote_write_option(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_run_gateway_server(
        *,
        host,
        port,
        output_dir,
        api_key,
        jwt_secret,
        jwt_issuer,
        jwt_audience,
        allow_remote_write_tools,
        slack_signing_secret,
        slack_allow_unsigned,
    ):
        captured["host"] = host
        captured["port"] = port
        captured["output_dir"] = output_dir
        captured["api_key"] = api_key
        captured["jwt_secret"] = jwt_secret
        captured["jwt_issuer"] = jwt_issuer
        captured["jwt_audience"] = jwt_audience
        captured["allow_remote_write_tools"] = allow_remote_write_tools
        captured["slack_signing_secret"] = slack_signing_secret
        captured["slack_allow_unsigned"] = slack_allow_unsigned

    import parallel_agents.gateway as gateway_module

    monkeypatch.setattr(gateway_module, "run_gateway_server", fake_run_gateway_server)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        [
            "gateway",
            "start",
            "--output-dir",
            str(tmp_path),
            "--allow-remote-write-tools",
        ],
    )

    assert result.exit_code == 0
    assert captured["allow_remote_write_tools"] is True


def test_gateway_start_passes_slack_options(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_run_gateway_server(
        *,
        host,
        port,
        output_dir,
        api_key,
        jwt_secret,
        jwt_issuer,
        jwt_audience,
        allow_remote_write_tools,
        slack_signing_secret,
        slack_allow_unsigned,
    ):
        captured["slack_signing_secret"] = slack_signing_secret
        captured["slack_allow_unsigned"] = slack_allow_unsigned

    import parallel_agents.gateway as gateway_module

    monkeypatch.setattr(gateway_module, "run_gateway_server", fake_run_gateway_server)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        [
            "gateway",
            "start",
            "--output-dir",
            str(tmp_path),
            "--slack-signing-secret",
            "slack-secret",
            "--allow-unsigned-slack",
        ],
    )

    assert result.exit_code == 0
    assert captured["slack_signing_secret"] == "slack-secret"
    assert captured["slack_allow_unsigned"] is True


def test_gateway_channel_inbound_json(monkeypatch):
    captured: dict[str, object] = {}

    def fake_gateway_http_json(gateway_url, method, path, payload=None, *, api_key=None, timeout_seconds=15.0):
        captured["gateway_url"] = gateway_url
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        captured["api_key"] = api_key
        return {
            "status": "pairing_required",
            "processed": False,
            "channel": "slack",
            "peer_id": "U123",
            "pairing_code": "ABC123",
            "expires_at": "2026-06-13T12:00:00+00:00",
        }

    monkeypatch.setattr(main_module, "_gateway_http_json", fake_gateway_http_json)
    runner = _runner()

    result = runner.invoke(
        main_module.cli,
        [
            "gateway",
            "channel",
            "inbound",
            "--gateway-url",
            "http://localhost:9999",
            "--api-key",
            "secret",
            "--channel",
            "slack",
            "--peer-id",
            "U123",
            "--message",
            "Review this repo",
            "--execute",
            "--json-output",
        ],
    )

    assert result.exit_code == 0
    assert captured["gateway_url"] == "http://localhost:9999"
    assert captured["method"] == "POST"
    assert captured["path"] == "/channels/inbound"
    assert captured["api_key"] == "secret"
    payload = captured["payload"]
    assert payload["channel"] == "slack"
    assert payload["peer_id"] == "U123"
    assert payload["message"] == "Review this repo"
    assert payload["execute"] is True
    output = json.loads(result.output)
    assert output["pairing_code"] == "ABC123"


def test_gateway_channel_approve_json(monkeypatch):
    captured: dict[str, object] = {}

    def fake_gateway_http_json(gateway_url, method, path, payload=None, *, api_key=None, timeout_seconds=15.0):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {
            "status": "approved",
            "channel": "slack",
            "peer_id": "U123",
            "approved_at": "2026-06-13T12:00:00+00:00",
            "approved_by": "operator",
        }

    monkeypatch.setattr(main_module, "_gateway_http_json", fake_gateway_http_json)
    runner = _runner()

    result = runner.invoke(
        main_module.cli,
        [
            "gateway",
            "channel",
            "approve",
            "--code",
            "ABC123",
            "--approved-by",
            "operator",
            "--json-output",
        ],
    )

    assert result.exit_code == 0
    assert captured["method"] == "POST"
    assert captured["path"] == "/channels/pairing/approve"
    assert captured["payload"] == {"code": "ABC123", "approved_by": "operator"}
    assert json.loads(result.output)["status"] == "approved"


def test_gateway_channel_peers_json(monkeypatch):
    captured: dict[str, object] = {}

    def fake_gateway_http_json(gateway_url, method, path, payload=None, *, api_key=None, timeout_seconds=15.0):
        captured["method"] = method
        captured["path"] = path
        return {
            "peers": [
                {
                    "channel": "slack",
                    "peer_id": "U123",
                    "approved_at": "2026-06-13T12:00:00+00:00",
                    "approved_by": "operator",
                }
            ],
            "count": 1,
        }

    monkeypatch.setattr(main_module, "_gateway_http_json", fake_gateway_http_json)
    runner = _runner()

    result = runner.invoke(
        main_module.cli,
        [
            "gateway",
            "channel",
            "peers",
            "--channel",
            "slack/team a",
            "--json-output",
        ],
    )

    assert result.exit_code == 0
    assert captured["method"] == "GET"
    assert captured["path"] == "/channels/peers?channel=slack%2Fteam+a"
    assert json.loads(result.output)["count"] == 1


def test_release_verify_json_success(monkeypatch, tmp_path):
    expected = {
        "project_root": str(tmp_path),
        "executed_steps": 3,
        "passed_steps": 3,
        "failed_steps": 0,
        "skipped_steps": 0,
        "steps": [
            {"name": "version-parity", "status": "passed", "detail": "all versions match (0.4.3)"},
            {"name": "ruff-check", "status": "passed", "detail": "ok"},
            {"name": "pytest", "status": "passed", "detail": "ok"},
        ],
    }

    def fake_run_release_verification(**kwargs):
        assert str(kwargs["project_root"]) == str(tmp_path)
        return expected

    monkeypatch.setattr(main_module, "_run_release_verification", fake_run_release_verification)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["release", "verify", "--project-root", str(tmp_path), "--json-output"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["failed_steps"] == 0
    assert payload["executed_steps"] == 3


def test_release_verify_exits_nonzero_when_failed(monkeypatch, tmp_path):
    def fake_run_release_verification(**kwargs):
        return {
            "project_root": str(tmp_path),
            "executed_steps": 1,
            "passed_steps": 0,
            "failed_steps": 1,
            "skipped_steps": 0,
            "steps": [
                {"name": "python-build", "status": "failed", "detail": "No module named build"},
            ],
        }

    monkeypatch.setattr(main_module, "_run_release_verification", fake_run_release_verification)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["release", "verify", "--project-root", str(tmp_path), "--json-output"],
    )
    assert result.exit_code == main_module.EXIT_RUNTIME_FAILURE


def test_check_release_version_parity(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    package_init = tmp_path / "src" / "parallel_agents" / "__init__.py"
    npm_package = tmp_path / "npm-wrapper" / "package.json"
    package_init.parent.mkdir(parents=True)
    npm_package.parent.mkdir(parents=True)

    pyproject.write_text(
        "\n".join(
            [
                "[project]",
                'name = "parallel-agents"',
                'version = "0.4.3"',
            ]
        ),
        encoding="utf-8",
    )
    package_init.write_text('__version__ = "0.4.3"\n', encoding="utf-8")
    npm_package.write_text('{"name":"parallel-agents","version":"0.4.3"}', encoding="utf-8")

    ok = main_module._check_release_version_parity(tmp_path)
    assert ok["status"] == "passed"

    package_init.write_text('__version__ = "0.4.2"\n', encoding="utf-8")
    mismatch = main_module._check_release_version_parity(tmp_path)
    assert mismatch["status"] == "failed"
    assert "mismatch" in mismatch["detail"]


def test_office_init_creates_project_workspace(tmp_path):
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["office", "init", "--project", str(tmp_path), "--name", "Demo Office", "--json-output"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["name"] == "Demo Office"
    assert (tmp_path / ".parallel-agents" / "project.json").exists()
    assert (tmp_path / ".parallel-agents" / "runs").is_dir()
    assert (tmp_path / ".parallel-agents" / "artifacts").is_dir()
    assert (tmp_path / ".parallel-agents" / "memory").is_dir()
    assert (tmp_path / ".parallel-agents" / "memory" / "decisions.jsonl").exists()
    assert (tmp_path / ".parallel-agents" / "memory" / "lessons.jsonl").exists()
    assert (tmp_path / ".parallel-agents" / "memory" / "policies.json").exists()


def test_office_status_reports_initialized_workspace(tmp_path):
    runner = _runner()
    init_result = runner.invoke(
        main_module.cli,
        ["office", "init", "--project", str(tmp_path), "--name", "Status Demo"],
    )
    assert init_result.exit_code == 0

    status_result = runner.invoke(
        main_module.cli,
        ["office", "status", "--project", str(tmp_path), "--json-output"],
    )

    assert status_result.exit_code == 0
    payload = json.loads(status_result.output)
    assert payload["initialized"] is True
    assert payload["project"]["name"] == "Status Demo"
    assert payload["directory_exists"]["runs"] is True
    assert payload["directory_exists"]["memory"] is True


def test_office_doctor_json_output(monkeypatch, tmp_path):
    expected = {
        "project_root": str(tmp_path),
        "office_dir": str(tmp_path / ".parallel-agents"),
        "office_initialized": True,
        "passed_checks": 4,
        "warning_checks": 1,
        "failed_checks": 0,
        "healthy": False,
        "checks": [
            {"name": "project-root", "status": "passed", "detail": str(tmp_path)},
            {"name": "tool:gh", "status": "warning", "detail": "not found in PATH"},
        ],
    }

    def fake_run_office_doctor(project_path):
        assert str(project_path) == str(tmp_path)
        return expected

    monkeypatch.setattr(main_module, "_run_office_doctor", fake_run_office_doctor)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["office", "doctor", "--project", str(tmp_path), "--json-output"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["warning_checks"] == 1
    assert payload["healthy"] is False


def test_office_doctor_strict_exits_nonzero(monkeypatch, tmp_path):
    def fake_run_office_doctor(project_path):
        return {
            "project_root": str(tmp_path),
            "office_dir": str(tmp_path / ".parallel-agents"),
            "office_initialized": False,
            "passed_checks": 1,
            "warning_checks": 1,
            "failed_checks": 1,
            "healthy": False,
            "checks": [
                {"name": "project-root", "status": "passed", "detail": str(tmp_path)},
                {"name": "office-initialized", "status": "failed", "detail": "run init"},
            ],
        }

    monkeypatch.setattr(main_module, "_run_office_doctor", fake_run_office_doctor)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["office", "doctor", "--project", str(tmp_path), "--strict", "--json-output"],
    )
    assert result.exit_code == main_module.EXIT_RUNTIME_FAILURE


def test_office_fix_setup_json_output(monkeypatch, tmp_path):
    expected = {
        "project_root": str(tmp_path),
        "before": {
            "office_initialized": False,
            "passed_checks": 1,
            "warning_checks": 0,
            "failed_checks": 1,
        },
        "after": {
            "office_initialized": True,
            "passed_checks": 4,
            "warning_checks": 1,
            "failed_checks": 0,
            "healthy": False,
        },
        "actions_taken": ["initialized_office_workspace"],
        "suggested_commands": ["gh auth login"],
    }

    def fake_run_office_setup_fix(project_path):
        assert str(project_path) == str(tmp_path)
        return expected

    monkeypatch.setattr(main_module, "run_office_setup_fix", fake_run_office_setup_fix)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["office", "fix-setup", "--project", str(tmp_path), "--json-output"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["actions_taken"] == ["initialized_office_workspace"]
    assert payload["after"]["failed_checks"] == 0


def test_office_fix_setup_strict_exits_nonzero(monkeypatch, tmp_path):
    def fake_run_office_setup_fix(_project_path):
        return {
            "project_root": str(tmp_path),
            "before": {"office_initialized": True},
            "after": {
                "office_initialized": True,
                "passed_checks": 2,
                "warning_checks": 1,
                "failed_checks": 0,
                "healthy": False,
            },
            "actions_taken": [],
            "suggested_commands": ["npm --version"],
        }

    monkeypatch.setattr(main_module, "run_office_setup_fix", fake_run_office_setup_fix)
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        ["office", "fix-setup", "--project", str(tmp_path), "--strict", "--json-output"],
    )
    assert result.exit_code == main_module.EXIT_RUNTIME_FAILURE


def test_office_home_and_artifacts_use_project_workspace(tmp_path):
    runner = _runner()
    init_result = runner.invoke(
        main_module.cli,
        ["office", "init", "--project", str(tmp_path), "--name", "Artifacts Demo"],
    )
    assert init_result.exit_code == 0

    office_output = tmp_path / ".parallel-agents"
    persist_company_artifact(
        office_output,
        "run-xyz",
        "roadmap",
        {"name": "Roadmap A", "items": []},
    )
    persist_company_artifact(
        office_output,
        "run-xyz",
        "issue-plan",
        {"issues": []},
    )
    memory_result = runner.invoke(
        main_module.cli,
        [
            "office",
            "memory",
            "add",
            "--project",
            str(tmp_path),
            "--kind",
            "decision",
            "--title",
            "Use office memory",
            "--content",
            "Capture cross-run decisions in workspace files.",
            "--json-output",
        ],
    )
    assert memory_result.exit_code == 0

    home_result = runner.invoke(
        main_module.cli,
        ["office", "home", "--project", str(tmp_path), "--json-output"],
    )
    assert home_result.exit_code == 0
    home_payload = json.loads(home_result.output)
    assert home_payload["run_count"] >= 1
    assert home_payload["artifact_count"] >= 2
    assert home_payload["memory_count"] >= 1
    assert home_payload["memory_counts"]["decision"] >= 1
    assert str(office_output) in home_payload["output_dir"]

    runs_result = runner.invoke(
        main_module.cli,
        ["office", "artifacts", "--project", str(tmp_path), "--json-output"],
    )
    assert runs_result.exit_code == 0
    runs_payload = json.loads(runs_result.output)
    assert runs_payload["run_count"] >= 1
    assert runs_payload["runs"][0]["run_id"] == "run-xyz"

    run_result = runner.invoke(
        main_module.cli,
        ["office", "artifacts", "--project", str(tmp_path), "--run-id", "run-xyz", "--json-output"],
    )
    assert run_result.exit_code == 0
    run_payload = json.loads(run_result.output)
    assert run_payload["count"] >= 2
    assert "roadmap" in run_payload["artifacts"]

    one_artifact_result = runner.invoke(
        main_module.cli,
        [
            "office",
            "artifacts",
            "--project",
            str(tmp_path),
            "--run-id",
            "run-xyz",
            "--artifact",
            "roadmap",
        ],
    )
    assert one_artifact_result.exit_code == 0
    artifact_payload = json.loads(one_artifact_result.output)
    assert artifact_payload["name"] == "Roadmap A"


def test_office_memory_add_list_search_and_policies(tmp_path):
    runner = _runner()
    init_result = runner.invoke(
        main_module.cli,
        ["office", "init", "--project", str(tmp_path), "--name", "Memory Demo"],
    )
    assert init_result.exit_code == 0

    add_result = runner.invoke(
        main_module.cli,
        [
            "office",
            "memory",
            "add",
            "--project",
            str(tmp_path),
            "--kind",
            "decision",
            "--title",
            "Use FastAPI Gateway",
            "--content",
            "Keep API local-first and reuse CLI execution primitives.",
            "--tags",
            "gateway,architecture",
            "--owner-role",
            "staff-engineer",
            "--source",
            "arch-rfc-12",
            "--run-id",
            "run-memory-1",
            "--json-output",
        ],
    )
    assert add_result.exit_code == 0
    entry = json.loads(add_result.output)
    assert entry["kind"] == "decision"
    assert entry["title"] == "Use FastAPI Gateway"

    list_result = runner.invoke(
        main_module.cli,
        [
            "office",
            "memory",
            "list",
            "--project",
            str(tmp_path),
            "--kind",
            "decision",
            "--json-output",
        ],
    )
    assert list_result.exit_code == 0
    list_payload = json.loads(list_result.output)
    assert list_payload["count"] == 1
    assert list_payload["entries"][0]["title"] == "Use FastAPI Gateway"

    search_result = runner.invoke(
        main_module.cli,
        [
            "office",
            "memory",
            "search",
            "--project",
            str(tmp_path),
            "--query",
            "local-first",
            "--json-output",
        ],
    )
    assert search_result.exit_code == 0
    search_payload = json.loads(search_result.output)
    assert search_payload["count"] == 1
    assert search_payload["entries"][0]["id"] == entry["id"]

    policies_path = tmp_path / "policies.json"
    policies_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "rules": [
                    {"id": "retain-decisions", "description": "Keep architecture decisions for 12 months"}
                ],
            }
        ),
        encoding="utf-8",
    )
    set_result = runner.invoke(
        main_module.cli,
        [
            "office",
            "memory",
            "policies",
            "--project",
            str(tmp_path),
            "--set-file",
            str(policies_path),
            "--json-output",
        ],
    )
    assert set_result.exit_code == 0
    set_payload = json.loads(set_result.output)
    assert isinstance(set_payload.get("updated_at"), str)
    assert len(set_payload.get("rules", [])) == 1

    get_result = runner.invoke(
        main_module.cli,
        ["office", "memory", "policies", "--project", str(tmp_path), "--json-output"],
    )
    assert get_result.exit_code == 0
    get_payload = json.loads(get_result.output)
    assert get_payload["rules"][0]["id"] == "retain-decisions"


def test_office_memory_requires_initialized_workspace(tmp_path):
    runner = _runner()
    result = runner.invoke(
        main_module.cli,
        [
            "office",
            "memory",
            "list",
            "--project",
            str(tmp_path),
            "--json-output",
        ],
    )
    assert result.exit_code == main_module.EXIT_RUNTIME_FAILURE
    assert "Project office is not initialized" in result.output


def test_office_onboard_json_initializes_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("parallel_agents.project_office.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("parallel_agents.onboarding.shutil.which", lambda name: f"/usr/bin/{name}")
    runner = _runner()

    result = runner.invoke(
        main_module.cli,
        [
            "office",
            "onboard",
            "--project",
            str(tmp_path),
            "--name",
            "Demo Office",
            "--skip-github-auth-check",
            "--json-output",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["project_root"] == str(tmp_path)
    assert payload["llm"]["status"] == "passed"
    assert payload["ready_for_local_run"] is True
    assert (tmp_path / ".parallel-agents" / "project.json").exists()
    assert any(item["label"] == "Run first safe analysis" for item in payload["next_actions"])


def test_office_onboard_strict_fails_without_model_auth(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("PA_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("parallel_agents.project_office.shutil.which", lambda name: None if name == "claude" else "tool")
    monkeypatch.setattr("parallel_agents.onboarding.shutil.which", lambda name: None if name == "claude" else "tool")
    runner = _runner()

    result = runner.invoke(
        main_module.cli,
        [
            "office",
            "onboard",
            "--project",
            str(tmp_path),
            "--skip-github-auth-check",
            "--strict",
            "--json-output",
        ],
    )

    assert result.exit_code == main_module.EXIT_RUNTIME_FAILURE
    payload = json.loads(result.output)
    assert payload["status"] == "needs_model_auth"
