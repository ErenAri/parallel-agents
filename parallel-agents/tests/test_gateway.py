from __future__ import annotations

import time

from fastapi.testclient import TestClient

from parallel_agents.company_artifacts import load_company_artifact, persist_company_artifact
from parallel_agents.company_workflows import build_roadmap, create_product_brief
from parallel_agents.gateway import GatewayStore, create_gateway_app


def _wait_for_status(
    client: TestClient,
    run_id: str,
    *,
    expected_statuses: set[str],
    timeout_seconds: float = 3.0,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"/runs/{run_id}")
        if response.status_code == 200:
            last = response.json()
            if last.get("status") in expected_statuses:
                return last
        time.sleep(0.02)
    return last


def test_gateway_health_and_project_creation(tmp_path):
    app = create_gateway_app(tmp_path)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    created = client.post("/projects", json={"name": "Demo", "repo_path": "/repo"}).json()
    assert created["name"] == "Demo"

    projects = client.get("/projects").json()
    assert projects["count"] == 1

    fetched = client.get(f"/projects/{created['id']}").json()
    assert fetched["repo_path"] == "/repo"


def test_gateway_company_idea_roadmap_plan_lifecycle(tmp_path):
    app = create_gateway_app(tmp_path)
    client = TestClient(app)

    idea_run = client.post(
        "/runs/company/idea",
        json={"run_id": "run-idea", "idea": "Build local gateway"},
    ).json()
    assert idea_run["status"] == "succeeded"
    assert idea_run["payload"]["artifact"]["title"] == "Build Local Gateway"

    roadmap_run = client.post(
        "/runs/company/roadmap",
        json={"run_id": "run-roadmap", "idea": "Build local gateway"},
    ).json()
    assert roadmap_run["status"] == "succeeded"
    roadmap = roadmap_run["payload"]["artifact"]

    plan_run = client.post(
        "/runs/company/plan",
        json={"run_id": "run-plan", "roadmap": roadmap, "repo": "owner/repo"},
    ).json()
    assert plan_run["status"] == "waiting_for_approval"
    assert plan_run["payload"]["artifact"]["approval_status"] == "pending"

    artifacts = client.get("/runs/run-plan/artifacts").json()
    assert "issue-plan" in artifacts["artifacts"]


def test_gateway_approval_events_and_apply_success(tmp_path, monkeypatch):
    app = create_gateway_app(tmp_path)
    client = TestClient(app)
    roadmap = build_roadmap(create_product_brief("Build approval flow")).model_dump(mode="json")
    client.post("/runs/company/plan", json={"run_id": "run-apply", "roadmap": roadmap, "repo": "owner/repo"})

    approval = client.post(
        "/runs/company/approve",
        json={"run_id": "run-apply", "approver": "lead", "approval_note": "ok"},
    ).json()
    assert approval["status"] == "succeeded"

    async def fake_execute_issue_plan(**kwargs):
        return {
            "repo": "owner/repo",
            "dry_run": False,
            "milestones": [],
            "issues": [{"title": "Issue", "created": True, "url": "https://example.test/1"}],
            "issue_plan": kwargs["issue_plan"],
            "create_milestones": kwargs["create_milestones"],
        }

    monkeypatch.setattr("parallel_agents.gateway._execute_issue_plan", fake_execute_issue_plan)
    applied = client.post("/runs/company/apply", json={"run_id": "run-apply"}).json()
    assert applied["status"] == "succeeded"
    assert applied["payload"]["artifact"]["approval_status"] == "applied"

    events = client.get("/runs/run-apply/events").json()
    assert events["count"] >= 1
    assert events["approval_audit_events"][0]["payload"]["approval_note"] == "ok"


def test_gateway_apply_waits_for_approval(tmp_path):
    app = create_gateway_app(tmp_path)
    client = TestClient(app)
    roadmap = build_roadmap(create_product_brief("Build approval flow")).model_dump(mode="json")
    client.post("/runs/company/plan", json={"run_id": "run-waiting", "roadmap": roadmap, "repo": "owner/repo"})

    result = client.post("/runs/company/apply", json={"run_id": "run-waiting"}).json()
    assert result["status"] == "waiting_for_approval"
    assert result["error_message"] == "plan is not approved"


def test_gateway_apply_blocks_policy_before_writes(tmp_path, monkeypatch):
    app = create_gateway_app(tmp_path)
    client = TestClient(app)
    roadmap = build_roadmap(create_product_brief("Build policy flow")).model_dump(mode="json")
    client.post("/runs/company/plan", json={"run_id": "run-policy", "roadmap": roadmap, "repo": "owner/repo"})
    client.post("/runs/company/approve", json={"run_id": "run-policy", "approver": "lead"})

    artifact = load_company_artifact(tmp_path, "run-policy", "issue-plan")
    assert artifact is not None
    artifact["apply_policy"]["label_allowlist"] = ["not-used"]
    persist_company_artifact(tmp_path, "run-policy", "issue-plan", artifact)

    async def should_not_run(**kwargs):
        raise AssertionError("GitHub writes should not be reached")

    monkeypatch.setattr("parallel_agents.gateway._execute_issue_plan", should_not_run)
    result = client.post("/runs/company/apply", json={"run_id": "run-policy"}).json()
    assert result["status"] == "blocked_by_policy"
    assert result["error_message"] == "policy check failed"
    assert result["payload"]["policy_violations"]


def test_gateway_store_persists_project_run_and_event(tmp_path):
    store = GatewayStore(tmp_path)
    project = store.create_project(name="Persisted")
    run = store.create_run(kind="test", project_id=project["id"], payload={"a": 1})
    store.update_run(run["id"], status="succeeded", payload={"b": 2})

    reloaded = GatewayStore(tmp_path)
    assert reloaded.get_project(project["id"])["name"] == "Persisted"
    assert reloaded.get_run(run["id"])["payload"]["b"] == 2
    assert reloaded.list_events(run["id"])


def test_gateway_list_runs_and_jobs_endpoint(tmp_path):
    app = create_gateway_app(tmp_path)
    client = TestClient(app)

    created = client.post(
        "/runs/company/idea",
        json={"run_id": "run-list", "idea": "Build run listing"},
    ).json()
    assert created["status"] == "succeeded"

    runs_payload = client.get("/runs").json()
    assert runs_payload["count"] >= 1
    assert any(item["id"] == "run-list" for item in runs_payload["runs"])

    jobs_payload = client.get("/runs/run-list/jobs").json()
    assert jobs_payload["count"] >= 1
    assert jobs_payload["jobs"][0]["attempt"] == 1


def test_gateway_cancel_and_retry_controls(tmp_path, monkeypatch):
    app = create_gateway_app(tmp_path)
    client = TestClient(app)

    original_create_brief = create_product_brief

    def slow_create_brief(idea: str, title: str | None = None):
        time.sleep(0.2)
        return original_create_brief(idea, title)

    monkeypatch.setattr("parallel_agents.gateway.create_product_brief", slow_create_brief)
    queued = client.post(
        "/runs/company/idea",
        json={"run_id": "run-cancel", "idea": "Build cancel flow", "wait": False},
    ).json()
    assert queued["status"] in {"queued", "running"}

    cancel_result = client.post("/runs/run-cancel/cancel", json={"reason": "manual"}).json()
    assert cancel_result["id"] == "run-cancel"

    cancelled = _wait_for_status(
        client,
        "run-cancel",
        expected_statuses={"failed", "succeeded"},
    )
    assert cancelled["status"] == "failed"
    assert cancelled["error_message"] == "run cancelled"

    roadmap = build_roadmap(create_product_brief("Build retry flow")).model_dump(mode="json")
    client.post("/runs/company/plan", json={"run_id": "run-retry", "roadmap": roadmap, "repo": "owner/repo"})
    client.post("/runs/company/approve", json={"run_id": "run-retry", "approver": "lead"})

    artifact = load_company_artifact(tmp_path, "run-retry", "issue-plan")
    assert artifact is not None
    artifact["apply_policy"]["label_allowlist"] = ["not-used"]
    persist_company_artifact(tmp_path, "run-retry", "issue-plan", artifact)

    blocked = client.post("/runs/company/apply", json={"run_id": "run-retry"}).json()
    assert blocked["status"] == "blocked_by_policy"

    artifact = load_company_artifact(tmp_path, "run-retry", "issue-plan")
    assert artifact is not None
    artifact.pop("apply_policy", None)
    persist_company_artifact(tmp_path, "run-retry", "issue-plan", artifact)

    async def fake_execute_issue_plan(**kwargs):
        return {
            "repo": "owner/repo",
            "dry_run": False,
            "milestones": [],
            "issues": [{"title": "Issue", "created": True, "url": "https://example.test/1"}],
            "issue_plan": kwargs["issue_plan"],
            "create_milestones": kwargs["create_milestones"],
        }

    monkeypatch.setattr("parallel_agents.gateway._execute_issue_plan", fake_execute_issue_plan)
    retried = client.post("/runs/run-retry/retry").json()
    assert retried["status"] == "succeeded"
    assert retried["attempt_count"] >= 2


def test_gateway_api_key_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("PA_GATEWAY_API_KEY", "gateway-secret")
    app = create_gateway_app(tmp_path)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["auth_required"] is True

    unauthorized = client.post("/projects", json={"name": "Blocked"})
    assert unauthorized.status_code == 401

    authorized = client.post(
        "/projects",
        json={"name": "Allowed"},
        headers={"x-pa-api-key": "gateway-secret"},
    )
    assert authorized.status_code == 200

    bearer = client.get(
        "/projects",
        headers={"Authorization": "Bearer gateway-secret"},
    )
    assert bearer.status_code == 200
    assert bearer.json()["count"] == 1
