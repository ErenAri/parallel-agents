from __future__ import annotations

from fastapi.testclient import TestClient

from parallel_agents.company_artifacts import load_company_artifact, persist_company_artifact
from parallel_agents.company_workflows import build_roadmap, create_product_brief
from parallel_agents.gateway import GatewayStore, create_gateway_app


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
