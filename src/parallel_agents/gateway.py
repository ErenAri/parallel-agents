from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from parallel_agents.company_artifacts import (
    append_company_artifact_event,
    list_company_artifact_paths,
    load_company_artifact,
    load_company_artifact_events,
    persist_company_artifact,
)
from parallel_agents.company_policy import (
    derive_policy_from_issue_plan,
    validate_issue_plan_against_policy,
)
from parallel_agents.company_workflows import (
    RoadmapPlan,
    build_issue_plan_from_roadmap,
    build_roadmap,
    create_product_brief,
)
from parallel_agents.tools.github_tools import parse_repo_ref

RUN_STATUSES = {
    "queued",
    "running",
    "waiting_for_approval",
    "blocked_by_policy",
    "succeeded",
    "failed",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GatewayStore:
    def __init__(self, output_dir: str | Path = ".parallel-agents-output") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.output_dir / "gateway.sqlite"
        self._init_db()

    def create_project(self, *, name: str, repo_path: str | None = None) -> dict[str, Any]:
        project_id = f"proj-{uuid.uuid4().hex[:12]}"
        created_at = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, repo_path, created_at) VALUES (?, ?, ?, ?)",
                (project_id, name, repo_path, created_at),
            )
        return self.get_project(project_id) or {
            "id": project_id,
            "name": name,
            "repo_path": repo_path,
            "created_at": created_at,
        }

    def list_projects(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return _row_to_dict(row) if row else None

    def create_run(
        self,
        *,
        kind: str,
        run_id: str | None = None,
        project_id: str | None = None,
        status: str = "queued",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (id, project_id, kind, status, created_at, updated_at, payload_json, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_run_id,
                    project_id,
                    kind,
                    status,
                    now,
                    now,
                    json.dumps(payload or {}, default=str),
                    None,
                ),
            )
            conn.execute(
                """
                INSERT INTO jobs (id, run_id, kind, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"job-{uuid.uuid4().hex[:12]}",
                    resolved_run_id,
                    kind,
                    status,
                    now,
                    now,
                ),
            )
        self.add_event(resolved_run_id, "run_created", {"kind": kind, "status": status})
        return self.get_run(resolved_run_id) or {"id": resolved_run_id, "status": status}

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        payload: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        if status not in RUN_STATUSES:
            raise ValueError(f"Unsupported run status: {status}")
        existing = self.get_run(run_id)
        if not existing:
            raise ValueError(f"Run not found: {run_id}")
        merged_payload = existing.get("payload", {})
        if payload:
            merged_payload.update(payload)
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, updated_at = ?, payload_json = ?, error_message = ?
                WHERE id = ?
                """,
                (status, now, json.dumps(merged_payload, default=str), error_message, run_id),
            )
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE run_id = ?",
                (status, now, run_id),
            )
        self.add_event(run_id, "run_status", {"status": status, "error_message": error_message})
        return self.get_run(run_id) or {"id": run_id, "status": status}

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        payload = _row_to_dict(row)
        payload["payload"] = json.loads(payload.pop("payload_json") or "{}")
        return payload

    def add_event(self, run_id: str, event: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event_payload = {
            "run_id": run_id,
            "event": event,
            "timestamp": _utc_now(),
            "payload": payload or {},
        }
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO events (run_id, timestamp, event, payload_json) VALUES (?, ?, ?, ?)",
                (
                    run_id,
                    event_payload["timestamp"],
                    event,
                    json.dumps(event_payload["payload"], default=str),
                ),
            )
            event_payload["id"] = cursor.lastrowid
        return event_payload

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            payload = _row_to_dict(row)
            payload["payload"] = json.loads(payload.pop("payload_json") or "{}")
            events.append(payload)
        return events

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    repo_path TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )


def create_gateway_app(output_dir: str | Path = ".parallel-agents-output"):
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:
        raise RuntimeError(
            "Gateway support requires FastAPI. Install with `pip install parallel-agents[gateway]`."
        ) from exc

    store = GatewayStore(output_dir)
    app = FastAPI(title="Parallel Agents Gateway", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "output_dir": str(store.output_dir.resolve()),
        }

    @app.post("/projects")
    def create_project(payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        return store.create_project(name=name, repo_path=payload.get("repo_path"))

    @app.get("/projects")
    def list_projects() -> dict[str, Any]:
        projects = store.list_projects()
        return {"projects": projects, "count": len(projects)}

    @app.get("/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="project not found")
        return project

    @app.post("/runs/company/idea")
    def run_company_idea(payload: dict[str, Any]) -> dict[str, Any]:
        run = store.create_run(
            kind="company.idea",
            run_id=payload.get("run_id"),
            project_id=payload.get("project_id"),
            status="running",
            payload=payload,
        )
        try:
            brief = create_product_brief(
                idea=str(payload.get("idea") or ""),
                title=payload.get("title") or None,
            )
            path = persist_company_artifact(store.output_dir, run["id"], "brief", brief)
            return store.update_run(
                run["id"],
                status="succeeded",
                payload={
                    "artifact": brief.model_dump(mode="json"),
                    "artifact_path": str(path),
                },
            )
        except Exception as exc:
            store.update_run(run["id"], status="failed", error_message=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/runs/company/roadmap")
    def run_company_roadmap(payload: dict[str, Any]) -> dict[str, Any]:
        run = store.create_run(
            kind="company.roadmap",
            run_id=payload.get("run_id"),
            project_id=payload.get("project_id"),
            status="running",
            payload=payload,
        )
        try:
            horizon_weeks = int(payload.get("horizon_weeks") or 12)
            brief = create_product_brief(
                idea=str(payload.get("idea") or ""),
                title=payload.get("title") or None,
            )
            roadmap = build_roadmap(brief, horizon_weeks=horizon_weeks)
            brief_path = persist_company_artifact(store.output_dir, run["id"], "brief", brief)
            roadmap_path = persist_company_artifact(store.output_dir, run["id"], "roadmap", roadmap)
            return store.update_run(
                run["id"],
                status="succeeded",
                payload={
                    "artifact": roadmap.model_dump(mode="json"),
                    "brief_artifact_path": str(brief_path),
                    "artifact_path": str(roadmap_path),
                },
            )
        except Exception as exc:
            store.update_run(run["id"], status="failed", error_message=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/runs/company/plan")
    def run_company_plan(payload: dict[str, Any]) -> dict[str, Any]:
        run = store.create_run(
            kind="company.plan",
            run_id=payload.get("run_id"),
            project_id=payload.get("project_id"),
            status="running",
            payload=payload,
        )
        try:
            roadmap_payload = payload.get("roadmap")
            if not isinstance(roadmap_payload, dict):
                raise ValueError("roadmap object is required")
            repo_ref = str(payload.get("repo") or "")
            parsed = parse_repo_ref(repo_ref)
            if not parsed:
                raise ValueError("repo must be owner/repo or a GitHub repository URL")
            owner, repo = parsed
            labels = payload.get("labels") or ["planning", "ai-agents"]
            roadmap = RoadmapPlan.model_validate(roadmap_payload)
            issue_plan = build_issue_plan_from_roadmap(roadmap, default_labels=list(labels))
            policy = derive_policy_from_issue_plan(f"{owner}/{repo}", issue_plan)

            from parallel_agents.main import _build_pending_company_issue_plan

            plan_payload = _build_pending_company_issue_plan(
                owner=owner,
                repo=repo,
                issue_plan=issue_plan,
                create_milestones=bool(payload.get("create_milestones", True)),
                apply_policy=policy,
            )
            plan_payload["run_id"] = run["id"]
            path = persist_company_artifact(store.output_dir, run["id"], "issue-plan", plan_payload)
            return store.update_run(
                run["id"],
                status="waiting_for_approval",
                payload={
                    "artifact": plan_payload,
                    "artifact_path": str(path),
                },
            )
        except Exception as exc:
            store.update_run(run["id"], status="failed", error_message=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/runs/company/approve")
    def run_company_approve(payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "")
        if not run_id:
            raise HTTPException(status_code=400, detail="run_id is required")
        artifact_name = str(payload.get("artifact") or "issue-plan")
        artifact = load_company_artifact(store.output_dir, run_id, artifact_name)
        if not artifact:
            raise HTTPException(status_code=404, detail="artifact not found")
        approved_at = _utc_now()
        artifact["approved"] = True
        artifact["approval_status"] = "approved"
        artifact["approved_at"] = approved_at
        artifact["approved_by"] = payload.get("approver") or "gateway-approval"
        if payload.get("approval_note"):
            artifact["approval_note"] = payload["approval_note"]
        audit_path = append_company_artifact_event(
            store.output_dir,
            run_id,
            artifact_name,
            {
                "event": "approval_granted",
                "run_id": run_id,
                "artifact": artifact_name,
                "approved_by": artifact["approved_by"],
                "approved_at": approved_at,
                "approval_note": payload.get("approval_note"),
            },
        )
        path = persist_company_artifact(store.output_dir, run_id, artifact_name, artifact)
        store.add_event(run_id, "approval_granted", {"artifact": artifact_name})
        return store.update_run(
            run_id,
            status="succeeded",
            payload={
                "artifact": artifact,
                "artifact_path": str(path),
                "approval_log_path": str(audit_path),
            },
        )

    @app.post("/runs/company/apply")
    async def run_company_apply(payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "")
        if not run_id:
            raise HTTPException(status_code=400, detail="run_id is required")
        artifact_name = str(payload.get("artifact") or "issue-plan")
        artifact = load_company_artifact(store.output_dir, run_id, artifact_name)
        if not artifact:
            raise HTTPException(status_code=404, detail="artifact not found")
        if artifact.get("requires_approval") and not artifact.get("approved"):
            return store.update_run(
                run_id,
                status="waiting_for_approval",
                error_message="plan is not approved",
            )
        parsed = parse_repo_ref(str(artifact.get("repo", "")))
        if not parsed:
            raise HTTPException(status_code=400, detail="artifact repo is invalid or missing")
        owner, repo = parsed
        issue_plan = artifact.get("issue_plan") or []
        policy = derive_policy_from_issue_plan(f"{owner}/{repo}", issue_plan)
        if isinstance(artifact.get("apply_policy"), dict):
            from parallel_agents.company_policy import CompanyApplyPolicy

            policy = CompanyApplyPolicy.model_validate(artifact["apply_policy"])
        violations = validate_issue_plan_against_policy(
            repo_ref=f"{owner}/{repo}",
            issue_plan=issue_plan,
            policy=policy,
        )
        if violations:
            return store.update_run(
                run_id,
                status="blocked_by_policy",
                payload={"policy_violations": violations},
                error_message="policy check failed",
            )

        try:
            result = await _execute_issue_plan(
                owner=owner,
                repo=repo,
                issue_plan=issue_plan,
                create_milestones=bool(artifact.get("create_milestones", True)),
            )
            result["approval_status"] = "applied"
            path = persist_company_artifact(store.output_dir, run_id, artifact_name, result)
            return store.update_run(
                run_id,
                status="succeeded",
                payload={
                    "artifact": result,
                    "artifact_path": str(path),
                },
            )
        except Exception as exc:
            store.update_run(run_id, status="failed", error_message=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        run = store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @app.get("/runs/{run_id}/artifacts")
    def get_run_artifacts(run_id: str) -> dict[str, Any]:
        artifacts = list_company_artifact_paths(store.output_dir, run_id)
        return {
            "run_id": run_id,
            "artifacts": artifacts,
            "count": len(artifacts),
        }

    @app.get("/runs/{run_id}/events")
    def get_run_events(run_id: str) -> dict[str, Any]:
        events = store.list_events(run_id)
        audit_events = load_company_artifact_events(store.output_dir, run_id, "issue-plan")
        return {
            "run_id": run_id,
            "events": events,
            "approval_audit_events": audit_events,
            "count": len(events) + len(audit_events),
        }

    return app


async def _execute_issue_plan(
    *,
    owner: str,
    repo: str,
    issue_plan: list[Any],
    create_milestones: bool,
) -> dict[str, Any]:
    from parallel_agents.main import _execute_company_issue_plan

    return await _execute_company_issue_plan(
        owner=owner,
        repo=repo,
        issue_plan=issue_plan,
        create_milestones=create_milestones,
        dry_run=False,
    )


def run_gateway_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8733,
    output_dir: str | Path = ".parallel-agents-output",
) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "Gateway support requires Uvicorn. Install with `pip install parallel-agents[gateway]`."
        ) from exc

    app = create_gateway_app(output_dir)
    uvicorn.run(app, host=host, port=port)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
