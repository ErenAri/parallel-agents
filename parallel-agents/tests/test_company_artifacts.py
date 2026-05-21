from __future__ import annotations

from parallel_agents.company_artifacts import (
    append_company_artifact_event,
    list_company_artifact_paths,
    load_company_artifact,
    load_company_artifact_events,
    load_company_artifact_index,
    persist_company_artifact,
)
from parallel_agents.company_workflows import create_product_brief


def test_persist_company_artifact_writes_index_and_payload(tmp_path):
    brief = create_product_brief("Build a product workflow")
    path = persist_company_artifact(
        output_dir=tmp_path,
        run_id="run-123",
        artifact_name="brief",
        artifact_payload=brief,
    )

    assert path.exists()
    index = load_company_artifact_index(tmp_path, "run-123")
    assert index is not None
    assert index.artifacts["brief"] == "brief.json"

    paths = list_company_artifact_paths(tmp_path, "run-123")
    assert "brief" in paths


def test_persist_multiple_artifacts_same_run(tmp_path):
    persist_company_artifact(
        output_dir=tmp_path,
        run_id="run-abc",
        artifact_name="brief",
        artifact_payload={"id": "b1"},
    )
    persist_company_artifact(
        output_dir=tmp_path,
        run_id="run-abc",
        artifact_name="roadmap",
        artifact_payload={"name": "roadmap"},
    )

    index = load_company_artifact_index(tmp_path, "run-abc")
    assert index is not None
    assert set(index.artifacts.keys()) == {"brief", "roadmap"}

    brief = load_company_artifact(tmp_path, "run-abc", "brief")
    assert brief is not None
    assert brief["id"] == "b1"


def test_append_company_artifact_event_creates_hash_chain(tmp_path):
    persist_company_artifact(
        output_dir=tmp_path,
        run_id="run-events",
        artifact_name="issue-plan",
        artifact_payload={"repo": "owner/repo"},
    )

    append_company_artifact_event(
        output_dir=tmp_path,
        run_id="run-events",
        artifact_name="issue-plan",
        event_payload={"event": "approved", "approved_by": "lead"},
    )
    append_company_artifact_event(
        output_dir=tmp_path,
        run_id="run-events",
        artifact_name="issue-plan",
        event_payload={"event": "applied", "applied_by": "release-bot"},
    )

    events = load_company_artifact_events(tmp_path, "run-events", "issue-plan")
    assert len(events) == 2
    assert events[0]["previous_hash"] is None
    assert events[1]["previous_hash"] == events[0]["hash"]

    index = load_company_artifact_index(tmp_path, "run-events")
    assert index is not None
    assert "issue-plan-audit-log" in index.artifacts
