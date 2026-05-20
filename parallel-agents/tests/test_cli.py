"""CLI integration tests for user-facing commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

import parallel_agents.main as main_module
import parallel_agents.mcp_installer as mcp_installer_module
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
