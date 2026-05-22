from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
import hashlib
import hmac
import inspect
import json
import os
import queue
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from parallel_agents.company_artifacts import (
    append_company_artifact_event,
    list_company_artifact_paths,
    load_company_artifact,
    load_company_artifact_events,
    persist_company_artifact,
)
from parallel_agents.company_policy import (
    CompanyApplyPolicy,
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

TERMINAL_RUN_STATUSES = {
    "waiting_for_approval",
    "blocked_by_policy",
    "succeeded",
    "failed",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _as_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _resolve_gateway_api_key(api_key: str | None) -> str | None:
    raw = api_key if api_key is not None else os.getenv("PA_GATEWAY_API_KEY")
    if raw is None:
        return None
    cleaned = str(raw).strip()
    return cleaned or None


def _resolve_gateway_jwt_secret(jwt_secret: str | None) -> str | None:
    raw = jwt_secret if jwt_secret is not None else os.getenv("PA_GATEWAY_JWT_SECRET")
    if raw is None:
        return None
    cleaned = str(raw).strip()
    return cleaned or None


def _resolve_gateway_jwt_issuer(jwt_issuer: str | None) -> str | None:
    raw = jwt_issuer if jwt_issuer is not None else os.getenv("PA_GATEWAY_JWT_ISSUER")
    if raw is None:
        return None
    cleaned = str(raw).strip()
    return cleaned or None


def _resolve_gateway_jwt_audience(jwt_audience: str | None) -> str | None:
    raw = (
        jwt_audience if jwt_audience is not None else os.getenv("PA_GATEWAY_JWT_AUDIENCE")
    )
    if raw is None:
        return None
    cleaned = str(raw).strip()
    return cleaned or None


def _resolve_gateway_allow_remote_write_tools(value: bool | str | None) -> bool:
    if value is None:
        return _as_bool(os.getenv("PA_GATEWAY_ALLOW_REMOTE_WRITE_TOOLS"), default=False)
    return _as_bool(value, default=False)


def _decode_b64url(segment: str) -> bytes:
    padded = segment + ("=" * (-len(segment) % 4))
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def _is_valid_hs256_jwt(
    token: str,
    *,
    secret: str,
    issuer: str | None,
    audience: str | None,
) -> bool:
    parts = token.split(".")
    if len(parts) != 3:
        return False
    encoded_header, encoded_payload, encoded_sig = parts
    if not encoded_header or not encoded_payload or not encoded_sig:
        return False

    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    expected_sig = base64.urlsafe_b64encode(
        hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    ).rstrip(b"=").decode("utf-8")
    if not hmac.compare_digest(expected_sig, encoded_sig):
        return False

    try:
        header = json.loads(_decode_b64url(encoded_header).decode("utf-8"))
        payload = json.loads(_decode_b64url(encoded_payload).decode("utf-8"))
    except Exception:
        return False
    if not isinstance(header, dict) or not isinstance(payload, dict):
        return False
    if str(header.get("alg", "")).upper() != "HS256":
        return False

    now = time.time()
    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and now >= float(exp):
        return False
    nbf = payload.get("nbf")
    if isinstance(nbf, (int, float)) and now < float(nbf):
        return False
    iat = payload.get("iat")
    if isinstance(iat, (int, float)) and now + 300 < float(iat):
        return False

    if issuer:
        if str(payload.get("iss", "")).strip() != issuer:
            return False

    if audience:
        aud = payload.get("aud")
        if isinstance(aud, str):
            if aud != audience:
                return False
        elif isinstance(aud, list):
            aud_values = [str(item) for item in aud]
            if audience not in aud_values:
                return False
        else:
            return False

    return True


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = json.loads(_decode_b64url(parts[1]).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


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
        if status not in RUN_STATUSES:
            raise ValueError(f"Unsupported run status: {status}")
        resolved_run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        if self.get_run(resolved_run_id):
            raise ValueError(f"Run already exists: {resolved_run_id}")
        now = _utc_now()
        attempt_count = 1
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, project_id, kind, status, created_at, updated_at, payload_json,
                    error_message, attempt_count, cancel_requested
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    attempt_count,
                    0,
                ),
            )
            conn.execute(
                """
                INSERT INTO jobs (
                    id, run_id, kind, status, created_at, updated_at, attempt, started_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"job-{uuid.uuid4().hex[:12]}",
                    resolved_run_id,
                    kind,
                    status,
                    now,
                    now,
                    attempt_count,
                    None,
                    None,
                ),
            )
        self.add_event(
            resolved_run_id,
            "run_created",
            {"kind": kind, "status": status, "attempt_count": attempt_count},
        )
        return self.get_run(resolved_run_id) or {"id": resolved_run_id, "status": status}

    def requeue_run(
        self,
        run_id: str,
        *,
        payload_override: dict[str, Any] | None = None,
        kind_override: str | None = None,
    ) -> dict[str, Any]:
        existing = self.get_run(run_id)
        if not existing:
            raise ValueError(f"Run not found: {run_id}")
        if existing.get("status") == "running":
            raise ValueError(f"Run is already running: {run_id}")

        merged_payload = dict(existing.get("payload") or {})
        if payload_override:
            merged_payload.update(payload_override)
        next_kind = str(kind_override or existing.get("kind") or "").strip()
        if not next_kind:
            raise ValueError(f"Run kind is missing for {run_id}")
        next_attempt = int(existing.get("attempt_count") or 0) + 1
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET kind = ?, status = ?, updated_at = ?, payload_json = ?, error_message = ?, attempt_count = ?, cancel_requested = ?
                WHERE id = ?
                """,
                (
                    next_kind,
                    "queued",
                    now,
                    json.dumps(merged_payload, default=str),
                    None,
                    next_attempt,
                    0,
                    run_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO jobs (
                    id, run_id, kind, status, created_at, updated_at, attempt, started_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"job-{uuid.uuid4().hex[:12]}",
                    run_id,
                    next_kind,
                    "queued",
                    now,
                    now,
                    next_attempt,
                    None,
                    None,
                ),
            )
        self.add_event(run_id, "run_requeued", {"attempt_count": next_attempt, "kind": next_kind})
        return self.get_run(run_id) or {"id": run_id, "status": "queued"}

    def mark_cancel_requested(self, run_id: str, *, reason: str | None = None) -> dict[str, Any]:
        existing = self.get_run(run_id)
        if not existing:
            raise ValueError(f"Run not found: {run_id}")
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET cancel_requested = ?, updated_at = ? WHERE id = ?",
                (1, now, run_id),
            )
        self.add_event(run_id, "cancel_requested", {"reason": reason or "user_requested"})
        return self.get_run(run_id) or existing

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

        merged_payload = dict(existing.get("payload") or {})
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
            self._update_latest_job_status(conn, run_id=run_id, status=status, now=now)

        self.add_event(run_id, "run_status", {"status": status, "error_message": error_message})
        return self.get_run(run_id) or {"id": run_id, "status": status}

    def list_runs(
        self,
        *,
        project_id: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM runs"
        clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, int(limit)))

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        runs: list[dict[str, Any]] = []
        for row in rows:
            item = _row_to_dict(row)
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
            item["cancel_requested"] = bool(item.get("cancel_requested"))
            runs.append(item)
        return runs

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        payload = _row_to_dict(row)
        payload["payload"] = json.loads(payload.pop("payload_json") or "{}")
        payload["cancel_requested"] = bool(payload.get("cancel_requested"))
        return payload

    def list_jobs(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE run_id = ? ORDER BY created_at ASC, id ASC",
                (run_id,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

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

    def add_access_audit(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        auth_mode: str,
        principal: str,
        allowed: bool,
        detail: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "timestamp": _utc_now(),
            "method": method,
            "path": path,
            "status_code": int(status_code),
            "auth_mode": auth_mode,
            "principal": principal,
            "allowed": bool(allowed),
            "detail": detail or "",
        }
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO access_audit (
                    timestamp, method, path, status_code, auth_mode, principal, allowed, detail
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["timestamp"],
                    payload["method"],
                    payload["path"],
                    payload["status_code"],
                    payload["auth_mode"],
                    payload["principal"],
                    1 if payload["allowed"] else 0,
                    payload["detail"],
                ),
            )
            payload["id"] = int(cursor.lastrowid)
        return payload

    def list_access_audit(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM access_audit
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = _row_to_dict(row)
            payload["allowed"] = bool(payload.get("allowed"))
            items.append(payload)
        return items

    def get_metrics_summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            project_count = int(conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"])
            run_count = int(conn.execute("SELECT COUNT(*) AS c FROM runs").fetchone()["c"])
            status_rows = conn.execute(
                "SELECT status, COUNT(*) AS c FROM runs GROUP BY status ORDER BY status ASC"
            ).fetchall()
            kind_rows = conn.execute(
                "SELECT kind, COUNT(*) AS c FROM runs GROUP BY kind ORDER BY kind ASC"
            ).fetchall()
            run_rows = conn.execute(
                """
                SELECT id, status, kind, created_at, updated_at
                FROM runs
                ORDER BY updated_at DESC
                LIMIT 1000
                """
            ).fetchall()

        status_counts = {str(row["status"]): int(row["c"]) for row in status_rows}
        kind_counts = {str(row["kind"]): int(row["c"]) for row in kind_rows}

        terminal_durations: list[float] = []
        for row in run_rows:
            status = str(row["status"])
            if status not in TERMINAL_RUN_STATUSES:
                continue
            created = _parse_iso_datetime(row["created_at"])
            updated = _parse_iso_datetime(row["updated_at"])
            if not created or not updated:
                continue
            duration_seconds = (updated - created).total_seconds()
            if duration_seconds >= 0:
                terminal_durations.append(duration_seconds)

        avg_terminal_run_seconds = (
            round(sum(terminal_durations) / len(terminal_durations), 3)
            if terminal_durations
            else None
        )
        succeeded_count = status_counts.get("succeeded", 0)
        failed_like_count = status_counts.get("failed", 0) + status_counts.get("blocked_by_policy", 0)
        success_rate = round(succeeded_count / run_count, 4) if run_count else None

        return {
            "project_count": project_count,
            "run_count": run_count,
            "status_counts": status_counts,
            "kind_counts": kind_counts,
            "succeeded_count": succeeded_count,
            "failed_like_count": failed_like_count,
            "waiting_for_approval_count": status_counts.get("waiting_for_approval", 0),
            "blocked_by_policy_count": status_counts.get("blocked_by_policy", 0),
            "success_rate": success_rate,
            "average_terminal_run_seconds": avg_terminal_run_seconds,
            "computed_at": _utc_now(),
        }

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
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
                    error_message TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 1,
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    started_at TEXT,
                    completed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS access_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    auth_mode TEXT NOT NULL,
                    principal TEXT NOT NULL,
                    allowed INTEGER NOT NULL,
                    detail TEXT
                );
                """
            )
            self._ensure_column(conn, "runs", "attempt_count", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "runs", "cancel_requested", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "jobs", "attempt", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "jobs", "started_at", "TEXT")
            self._ensure_column(conn, "jobs", "completed_at", "TEXT")

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {str(row["name"]).lower() for row in rows}
        if column.lower() in existing:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _update_latest_job_status(
        self,
        conn: sqlite3.Connection,
        *,
        run_id: str,
        status: str,
        now: str,
    ) -> None:
        latest = conn.execute(
            "SELECT id, started_at FROM jobs WHERE run_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if not latest:
            return
        job_id = str(latest["id"])
        started_at = latest["started_at"]
        if status == "running":
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ?, started_at = COALESCE(started_at, ?) WHERE id = ?",
                (status, now, now, job_id),
            )
            return
        if status in TERMINAL_RUN_STATUSES:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, updated_at = ?, started_at = COALESCE(started_at, ?), completed_at = COALESCE(completed_at, ?)
                WHERE id = ?
                """,
                (status, now, started_at or now, now, job_id),
            )
            return
        conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, job_id),
        )


class GatewayJobRunner:
    def __init__(
        self,
        *,
        store: GatewayStore,
        run_handler: Callable[[dict[str, Any]], tuple[str, dict[str, Any] | None, str | None]],
    ) -> None:
        self._store = store
        self._run_handler = run_handler
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stopped = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stopped.clear()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="parallel-agents-gateway-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout_seconds: float = 2.0) -> None:
        if not self._thread:
            return
        self._stopped.set()
        self._queue.put(None)
        self._thread.join(timeout=timeout_seconds)

    def enqueue(self, run_id: str) -> None:
        self._queue.put(run_id)
        self._store.add_event(run_id, "job_enqueued", {})

    def wait_for_terminal(self, run_id: str, *, timeout_seconds: float = 30.0) -> dict[str, Any] | None:
        deadline = time.monotonic() + max(0.1, timeout_seconds)
        while time.monotonic() < deadline:
            run = self._store.get_run(run_id)
            if run and str(run.get("status")) in TERMINAL_RUN_STATUSES:
                return run
            time.sleep(0.02)
        return self._store.get_run(run_id)

    def _worker_loop(self) -> None:
        while not self._stopped.is_set():
            run_id = self._queue.get()
            if run_id is None:
                self._queue.task_done()
                break
            try:
                self._process_one(run_id)
            finally:
                self._queue.task_done()

    def _process_one(self, run_id: str) -> None:
        run = self._store.get_run(run_id)
        if not run:
            return
        status = str(run.get("status") or "")
        if status not in {"queued", "running"}:
            return
        if bool(run.get("cancel_requested")):
            self._store.add_event(run_id, "run_cancelled", {"stage": "before_start"})
            self._store.update_run(run_id, status="failed", error_message="run cancelled")
            return

        self._store.update_run(run_id, status="running", error_message=None)
        self._store.add_event(
            run_id,
            "run_started",
            {"kind": run.get("kind"), "attempt_count": run.get("attempt_count")},
        )

        final_status = "failed"
        final_payload: dict[str, Any] | None = None
        final_error = None
        try:
            final_status, final_payload, final_error = self._run_handler(run)
        except Exception as exc:  # pragma: no cover - defensive boundary
            final_status = "failed"
            final_error = str(exc)

        updated = self._store.get_run(run_id)
        if updated and bool(updated.get("cancel_requested")):
            self._store.add_event(run_id, "run_cancelled", {"stage": "after_execution"})
            final_status = "failed"
            final_error = "run cancelled"

        if final_status not in RUN_STATUSES:
            final_status = "failed"
            final_error = final_error or f"invalid run status from handler: {final_status}"

        self._store.update_run(
            run_id,
            status=final_status,
            payload=final_payload,
            error_message=final_error,
        )
        self._store.add_event(run_id, "run_completed", {"status": final_status})


def create_gateway_app(
    output_dir: str | Path = ".parallel-agents-output",
    api_key: str | None = None,
    jwt_secret: str | None = None,
    jwt_issuer: str | None = None,
    jwt_audience: str | None = None,
    allow_remote_write_tools: bool | str | None = None,
):
    try:
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.responses import JSONResponse
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "Gateway support requires FastAPI. Install with `pip install parallel-agents[gateway]`."
        ) from exc

    store = GatewayStore(output_dir)
    resolved_api_key = _resolve_gateway_api_key(api_key)
    resolved_jwt_secret = _resolve_gateway_jwt_secret(jwt_secret)
    resolved_jwt_issuer = _resolve_gateway_jwt_issuer(jwt_issuer)
    resolved_jwt_audience = _resolve_gateway_jwt_audience(jwt_audience)
    resolved_allow_remote_write_tools = _resolve_gateway_allow_remote_write_tools(
        allow_remote_write_tools
    )

    def _run_company_idea(run: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str | None]:
        payload = dict(run.get("payload") or {})
        idea = str(payload.get("idea") or "").strip()
        if not idea:
            raise ValueError("idea is required")

        brief = create_product_brief(
            idea=idea,
            title=payload.get("title") or None,
        )
        path = persist_company_artifact(store.output_dir, run["id"], "brief", brief)
        return (
            "succeeded",
            {
                "artifact": brief.model_dump(mode="json"),
                "artifact_path": str(path),
            },
            None,
        )

    def _run_company_roadmap(run: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str | None]:
        payload = dict(run.get("payload") or {})
        idea = str(payload.get("idea") or "").strip()
        if not idea:
            raise ValueError("idea is required")
        horizon_weeks = int(payload.get("horizon_weeks") or 12)
        brief = create_product_brief(
            idea=idea,
            title=payload.get("title") or None,
        )
        roadmap = build_roadmap(brief, horizon_weeks=horizon_weeks)
        brief_path = persist_company_artifact(store.output_dir, run["id"], "brief", brief)
        roadmap_path = persist_company_artifact(store.output_dir, run["id"], "roadmap", roadmap)
        return (
            "succeeded",
            {
                "artifact": roadmap.model_dump(mode="json"),
                "brief_artifact_path": str(brief_path),
                "artifact_path": str(roadmap_path),
            },
            None,
        )

    def _run_company_plan(run: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str | None]:
        payload = dict(run.get("payload") or {})
        roadmap_payload = payload.get("roadmap")
        if not isinstance(roadmap_payload, dict):
            raise ValueError("roadmap object is required")

        repo_ref = str(payload.get("repo") or "")
        parsed = parse_repo_ref(repo_ref)
        if not parsed:
            raise ValueError("repo must be owner/repo or a GitHub repository URL")
        owner, repo = parsed

        labels = payload.get("labels") or ["planning", "ai-agents"]
        label_list = list(labels) if isinstance(labels, list) else ["planning", "ai-agents"]
        roadmap = RoadmapPlan.model_validate(roadmap_payload)
        issue_plan = build_issue_plan_from_roadmap(roadmap, default_labels=label_list)
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
        return (
            "waiting_for_approval",
            {
                "artifact": plan_payload,
                "artifact_path": str(path),
            },
            None,
        )

    def _run_company_approve(run: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str | None]:
        payload = dict(run.get("payload") or {})
        run_id = str(payload.get("run_id") or run["id"])
        artifact_name_override = payload.get("artifact")
        artifact_name = (
            str(artifact_name_override).strip()
            if isinstance(artifact_name_override, str) and str(artifact_name_override).strip()
            else "issue-plan"
        )
        artifact = load_company_artifact(store.output_dir, run_id, artifact_name)
        if not artifact:
            raise ValueError("artifact not found")

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
        return (
            "succeeded",
            {
                "artifact": artifact,
                "artifact_path": str(path),
                "approval_log_path": str(audit_path),
            },
            None,
        )

    def _run_company_apply(run: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str | None]:
        payload = dict(run.get("payload") or {})
        run_id = str(payload.get("run_id") or run["id"])
        artifact_name_override = payload.get("artifact")
        artifact_name = (
            str(artifact_name_override).strip()
            if isinstance(artifact_name_override, str) and str(artifact_name_override).strip()
            else "issue-plan"
        )
        artifact = load_company_artifact(store.output_dir, run_id, artifact_name)
        if not artifact:
            raise ValueError("artifact not found")

        if artifact.get("requires_approval") and not artifact.get("approved"):
            return ("waiting_for_approval", None, "plan is not approved")

        parsed = parse_repo_ref(str(artifact.get("repo", "")))
        if not parsed:
            raise ValueError("artifact repo is invalid or missing")
        owner, repo = parsed
        issue_plan = artifact.get("issue_plan") or []

        policy = derive_policy_from_issue_plan(f"{owner}/{repo}", issue_plan)
        if isinstance(artifact.get("apply_policy"), dict):
            policy = CompanyApplyPolicy.model_validate(artifact["apply_policy"])
        violations = validate_issue_plan_against_policy(
            repo_ref=f"{owner}/{repo}",
            issue_plan=issue_plan,
            policy=policy,
        )
        if violations:
            return (
                "blocked_by_policy",
                {"policy_violations": violations},
                "policy check failed",
            )

        result = asyncio.run(
            _execute_issue_plan(
                owner=owner,
                repo=repo,
                issue_plan=issue_plan,
                create_milestones=bool(artifact.get("create_milestones", True)),
            )
        )
        result["approval_status"] = "applied"
        path = persist_company_artifact(store.output_dir, run_id, artifact_name, result)
        return (
            "succeeded",
            {
                "artifact": result,
                "artifact_path": str(path),
            },
            None,
        )

    def _run_handler(run: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str | None]:
        kind = str(run.get("kind") or "")
        if kind == "company.idea":
            return _run_company_idea(run)
        if kind == "company.roadmap":
            return _run_company_roadmap(run)
        if kind == "company.plan":
            return _run_company_plan(run)
        if kind == "company.approve":
            return _run_company_approve(run)
        if kind == "company.apply":
            return _run_company_apply(run)
        raise ValueError(f"unsupported run kind: {kind}")

    runner = GatewayJobRunner(store=store, run_handler=_run_handler)
    runner.start()

    @asynccontextmanager
    async def _lifespan(_app: Any):
        try:
            yield
        finally:
            runner.stop()

    app = FastAPI(
        title="Parallel Agents Gateway",
        version="0.1.0",
        lifespan=_lifespan,
    )

    def _request_auth_context(request: Request) -> tuple[bool, str, str]:
        if not resolved_api_key and not resolved_jwt_secret:
            return True, "none", "anonymous"

        direct = request.headers.get("x-pa-api-key")
        if (
            resolved_api_key
            and isinstance(direct, str)
            and direct
            and hmac.compare_digest(direct, resolved_api_key)
        ):
            return True, "api_key", "api-key"

        auth_header = request.headers.get("authorization")
        if isinstance(auth_header, str) and auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            if resolved_api_key and token and hmac.compare_digest(token, resolved_api_key):
                return True, "api_key", "api-key"
            if resolved_jwt_secret and token and _is_valid_hs256_jwt(
                token,
                secret=resolved_jwt_secret,
                issuer=resolved_jwt_issuer,
                audience=resolved_jwt_audience,
            ):
                claims = _decode_jwt_payload(token) or {}
                principal = str(
                    claims.get("sub")
                    or claims.get("client_id")
                    or claims.get("email")
                    or "jwt-subject"
                )
                return True, "jwt_hs256", principal
        return False, "none", "anonymous"

    @app.middleware("http")
    async def _api_key_auth_middleware(request: Request, call_next):
        path = request.url.path
        authorized, auth_mode, principal = _request_auth_context(request)
        auth_required = bool(resolved_api_key or resolved_jwt_secret)
        bypass_auth = (not auth_required) or (path == "/health")

        if bypass_auth or authorized:
            response = await call_next(request)
            store.add_access_audit(
                method=request.method,
                path=path,
                status_code=int(response.status_code),
                auth_mode=auth_mode,
                principal=principal,
                allowed=True,
            )
            return response

        store.add_access_audit(
            method=request.method,
            path=path,
            status_code=401,
            auth_mode=auth_mode,
            principal=principal,
            allowed=False,
            detail="gateway auth required",
        )
        return JSONResponse(status_code=401, content={"detail": "gateway auth required"})

    def _submit_run(
        kind: str,
        payload: dict[str, Any],
        *,
        reuse_existing: bool = False,
        require_existing: bool = False,
    ) -> dict[str, Any]:
        run_id_value = payload.get("run_id")
        run_id = str(run_id_value).strip() if run_id_value is not None else ""
        existing = store.get_run(run_id) if run_id else None
        if existing:
            if not reuse_existing:
                raise HTTPException(status_code=409, detail=f"run already exists: {run_id}")
            try:
                run = store.requeue_run(
                    run_id,
                    payload_override=payload,
                    kind_override=kind,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            if require_existing:
                raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
            try:
                run = store.create_run(
                    kind=kind,
                    run_id=run_id if run_id else None,
                    project_id=payload.get("project_id"),
                    status="queued",
                    payload=payload,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        runner.enqueue(run["id"])

        wait_for_result = _as_bool(payload.get("wait"), default=True)
        if not wait_for_result:
            return store.get_run(run["id"]) or run

        timeout = payload.get("wait_timeout_seconds")
        try:
            timeout_seconds = float(timeout) if timeout is not None else 30.0
        except (TypeError, ValueError):
            timeout_seconds = 30.0
        return runner.wait_for_terminal(run["id"], timeout_seconds=timeout_seconds) or run

    @app.get("/health")
    def health() -> dict[str, Any]:
        auth_modes: list[str] = []
        if resolved_api_key:
            auth_modes.append("api_key")
        if resolved_jwt_secret:
            auth_modes.append("jwt_hs256")
        return {
            "status": "ok",
            "output_dir": str(store.output_dir.resolve()),
            "worker_alive": bool(runner._thread and runner._thread.is_alive()),
            "auth_required": bool(resolved_api_key or resolved_jwt_secret),
            "auth_modes": auth_modes,
            "allow_remote_write_tools": resolved_allow_remote_write_tools,
        }

    def _gateway_mcp_tools_catalog() -> list[dict[str, Any]]:
        from parallel_agents.mcp_server import TOOL_CATALOG

        catalog: list[dict[str, Any]] = []
        for entry in TOOL_CATALOG:
            item = dict(entry)
            is_write = str(item.get("access")) == "write"
            item["remote_enabled"] = (not is_write) or resolved_allow_remote_write_tools
            catalog.append(item)
        return catalog

    def _invoke_mcp_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        from parallel_agents import mcp_server

        tool_fn = getattr(mcp_server, tool_name, None)
        if tool_fn is None or not inspect.iscoroutinefunction(tool_fn):
            raise ValueError(f"tool not found: {tool_name}")

        signature = inspect.signature(tool_fn)
        kwargs: dict[str, Any] = {}
        for name in signature.parameters:
            if name in payload:
                kwargs[name] = payload[name]
        missing_required = [
            name
            for name, param in signature.parameters.items()
            if param.default is inspect._empty and name not in kwargs
        ]
        if missing_required:
            joined = ", ".join(sorted(missing_required))
            raise ValueError(f"missing required tool parameter(s): {joined}")

        raw_output = asyncio.run(tool_fn(**kwargs))
        parsed_output: Any = raw_output
        is_json = False
        if isinstance(raw_output, str):
            try:
                parsed_output = json.loads(raw_output)
                is_json = True
            except json.JSONDecodeError:
                parsed_output = raw_output
        return {
            "tool": tool_name,
            "response": parsed_output,
            "response_is_json": is_json,
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

    @app.get("/mcp/tools")
    def list_mcp_tools() -> dict[str, Any]:
        tools = _gateway_mcp_tools_catalog()
        return {
            "tools": tools,
            "count": len(tools),
            "allow_remote_write_tools": resolved_allow_remote_write_tools,
        }

    @app.post("/mcp/tools/{tool_name}")
    def call_mcp_tool(tool_name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        request_payload = dict(payload) if isinstance(payload, dict) else {}
        tools = {str(item.get("name")): item for item in _gateway_mcp_tools_catalog()}
        tool_meta = tools.get(tool_name)
        if not tool_meta:
            raise HTTPException(status_code=404, detail=f"unknown mcp tool: {tool_name}")

        if str(tool_meta.get("access")) == "write" and not resolved_allow_remote_write_tools:
            store.add_access_audit(
                method="POST",
                path=f"/mcp/tools/{tool_name}",
                status_code=403,
                auth_mode="policy",
                principal="gateway",
                allowed=False,
                detail="remote write MCP tools disabled",
            )
            raise HTTPException(status_code=403, detail="remote write MCP tools are disabled")

        try:
            response_payload = _invoke_mcp_tool(tool_name, request_payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return {
            "tool": tool_name,
            "access": tool_meta.get("access"),
            "approval_required": bool(tool_meta.get("approval_required")),
            "response": response_payload["response"],
            "response_is_json": bool(response_payload["response_is_json"]),
        }

    @app.post("/runs/company/idea")
    def run_company_idea(payload: dict[str, Any]) -> dict[str, Any]:
        return _submit_run("company.idea", payload)

    @app.post("/runs/company/roadmap")
    def run_company_roadmap(payload: dict[str, Any]) -> dict[str, Any]:
        return _submit_run("company.roadmap", payload)

    @app.post("/runs/company/plan")
    def run_company_plan(payload: dict[str, Any]) -> dict[str, Any]:
        return _submit_run("company.plan", payload)

    @app.post("/runs/company/approve")
    def run_company_approve(payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "")
        if not run_id:
            raise HTTPException(status_code=400, detail="run_id is required")
        payload = dict(payload)
        payload.setdefault("run_id", run_id)
        return _submit_run(
            "company.approve",
            payload,
            reuse_existing=True,
            require_existing=True,
        )

    @app.post("/runs/company/apply")
    def run_company_apply(payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "")
        if not run_id:
            raise HTTPException(status_code=400, detail="run_id is required")
        payload = dict(payload)
        payload.setdefault("run_id", run_id)
        return _submit_run(
            "company.apply",
            payload,
            reuse_existing=True,
            require_existing=True,
        )

    @app.get("/runs")
    def list_runs(
        project_id: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        runs = store.list_runs(
            project_id=project_id,
            kind=kind,
            status=status,
            limit=limit,
        )
        return {"runs": runs, "count": len(runs)}

    @app.get("/metrics/summary")
    def metrics_summary() -> dict[str, Any]:
        return store.get_metrics_summary()

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        run = store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @app.post("/runs/{run_id}/cancel")
    def cancel_run(run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        reason = None
        if isinstance(payload, dict):
            reason = str(payload.get("reason") or "").strip() or None
        try:
            run = store.mark_cancel_requested(run_id, reason=reason)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if run.get("status") == "queued":
            store.add_event(run_id, "run_cancelled", {"stage": "queued"})
            return store.update_run(run_id, status="failed", error_message="run cancelled")
        return run

    @app.post("/runs/{run_id}/retry")
    def retry_run(run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        run = store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        status = str(run.get("status") or "")
        if status not in {"failed", "blocked_by_policy", "waiting_for_approval"}:
            raise HTTPException(status_code=409, detail=f"run status '{status}' is not retryable")

        payload_override = payload if isinstance(payload, dict) else None
        try:
            requeued = store.requeue_run(run_id, payload_override=payload_override)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        runner.enqueue(requeued["id"])

        wait_for_result = True
        if isinstance(payload, dict):
            wait_for_result = _as_bool(payload.get("wait"), default=True)
        if wait_for_result:
            timeout = None
            if isinstance(payload, dict):
                timeout = payload.get("wait_timeout_seconds")
            try:
                timeout_seconds = float(timeout) if timeout is not None else 30.0
            except (TypeError, ValueError):
                timeout_seconds = 30.0
            return runner.wait_for_terminal(requeued["id"], timeout_seconds=timeout_seconds) or requeued
        return store.get_run(requeued["id"]) or requeued

    @app.get("/runs/{run_id}/artifacts/{artifact_name}")
    def get_run_artifact(run_id: str, artifact_name: str) -> dict[str, Any]:
        run = store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        artifact = load_company_artifact(store.output_dir, run_id, artifact_name)
        if artifact is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return {
            "run_id": run_id,
            "artifact_name": artifact_name,
            "artifact": artifact,
        }

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

    @app.get("/runs/{run_id}/jobs")
    def get_run_jobs(run_id: str) -> dict[str, Any]:
        run = store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        jobs = store.list_jobs(run_id)
        return {"run_id": run_id, "jobs": jobs, "count": len(jobs)}

    @app.get("/audit/access")
    def get_access_audit(limit: int = 200) -> dict[str, Any]:
        events = store.list_access_audit(limit=limit)
        return {
            "events": events,
            "count": len(events),
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
    api_key: str | None = None,
    jwt_secret: str | None = None,
    jwt_issuer: str | None = None,
    jwt_audience: str | None = None,
    allow_remote_write_tools: bool | str | None = None,
) -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "Gateway support requires Uvicorn. Install with `pip install parallel-agents[gateway]`."
        ) from exc

    app = create_gateway_app(
        output_dir,
        api_key=api_key,
        jwt_secret=jwt_secret,
        jwt_issuer=jwt_issuer,
        jwt_audience=jwt_audience,
        allow_remote_write_tools=allow_remote_write_tools,
    )
    uvicorn.run(app, host=host, port=port)
