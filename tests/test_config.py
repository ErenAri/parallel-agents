"""Unit tests for configuration system."""

from __future__ import annotations

from parallel_agents.config import (
    DEFAULT_ARTIFACT_DIR,
    LEGACY_ARTIFACT_DIR,
    PipelineConfig,
    WorkerConfig,
    migrate_legacy_artifact_dir,
)


class TestWorkerConfig:
    def test_defaults(self):
        wc = WorkerConfig()
        assert wc.enabled is True
        assert wc.model == "sonnet"
        assert wc.max_turns == 15
        assert wc.timeout_seconds == 300

    def test_custom(self):
        wc = WorkerConfig(enabled=False, model="opus", max_turns=30, timeout_seconds=600)
        assert wc.enabled is False
        assert wc.model == "opus"


class TestPipelineConfig:
    def test_defaults(self):
        config = PipelineConfig()
        assert config.planner_model == "opus"
        assert config.judge_model == "opus"
        assert config.max_parallel_workers == 4
        assert config.max_retries == 2
        assert config.parse_retry_attempts == 1
        assert config.store_backend == "file"
        assert config.permission_mode == "default"
        assert len(config.workers) == 8

    def test_all_workers_present(self):
        config = PipelineConfig()
        expected = {"security", "test", "perf", "devops", "arch", "docs", "code", "review"}
        assert set(config.workers.keys()) == expected

    def test_code_worker_uses_opus(self):
        config = PipelineConfig()
        assert config.workers["code"].model == "opus"

    def test_all_workers_enabled_by_default(self):
        config = PipelineConfig()
        for name, wc in config.workers.items():
            assert wc.enabled is True, f"{name} should be enabled by default"

    def test_custom_workers(self):
        config = PipelineConfig(workers={
            "security": WorkerConfig(enabled=True),
            "code": WorkerConfig(enabled=True, model="haiku"),
        })
        assert len(config.workers) == 2
        assert config.workers["code"].model == "haiku"

    def test_store_backend_option(self):
        config = PipelineConfig(store_backend="sqlite")
        assert config.store_backend == "sqlite"

    def test_output_dir_defaults_to_unified_root(self):
        config = PipelineConfig()
        assert config.output_dir == DEFAULT_ARTIFACT_DIR == ".parallel-agents"


class TestMigrateLegacyArtifactDir:
    def test_no_legacy_dir_is_noop(self, tmp_path):
        result = migrate_legacy_artifact_dir(tmp_path)
        assert result["migrated"] is False
        assert result["reason"] == "no-legacy-dir"

    def test_renames_legacy_onto_unified_root(self, tmp_path):
        legacy = tmp_path / LEGACY_ARTIFACT_DIR
        legacy.mkdir()
        (legacy / "marker.txt").write_text("keep me", encoding="utf-8")

        result = migrate_legacy_artifact_dir(tmp_path)
        assert result["migrated"] is True
        target = tmp_path / DEFAULT_ARTIFACT_DIR
        assert target.exists()
        assert (target / "marker.txt").read_text(encoding="utf-8") == "keep me"
        assert not legacy.exists()

    def test_refuses_when_target_exists(self, tmp_path):
        (tmp_path / LEGACY_ARTIFACT_DIR).mkdir()
        (tmp_path / DEFAULT_ARTIFACT_DIR).mkdir()

        result = migrate_legacy_artifact_dir(tmp_path)
        assert result["migrated"] is False
        assert result["reason"] == "target-exists"
        # never merges or overwrites: both dirs remain untouched
        assert (tmp_path / LEGACY_ARTIFACT_DIR).exists()
        assert (tmp_path / DEFAULT_ARTIFACT_DIR).exists()
