from __future__ import annotations

import asyncio
import json

import pytest

from parallel_agents.desktop.services import engine as engine_module
from parallel_agents.desktop.services.engine import EngineService
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
