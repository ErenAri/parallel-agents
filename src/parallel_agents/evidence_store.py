from __future__ import annotations

import json
import os
import sqlite3
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from parallel_agents.models import (
    FinalOutput,
    RunManifest,
    TaskPlan,
    WorkerResult,
)


class BaseEvidenceStore(ABC):
    """Abstract interface for evidence stores."""

    @abstractmethod
    def save_manifest(self, manifest: RunManifest) -> None: ...

    @abstractmethod
    def load_manifest(self) -> RunManifest | None: ...

    @abstractmethod
    def save_plan(self, plan: TaskPlan) -> None: ...

    @abstractmethod
    def load_plan(self) -> TaskPlan | None: ...

    @abstractmethod
    def save_worker_result(self, result: WorkerResult) -> None: ...

    @abstractmethod
    def load_worker_result(self, worker_name: str) -> WorkerResult | None: ...

    @abstractmethod
    def load_all_worker_results(self) -> dict[str, WorkerResult]: ...

    @abstractmethod
    def save_final_output(self, output: FinalOutput) -> None: ...

    @abstractmethod
    def load_final_output(self) -> FinalOutput | None: ...

    @abstractmethod
    def append_trace(self, agent_name: str, entry: dict[str, Any]) -> None: ...


class EvidenceStore(BaseEvidenceStore):
    """File-based evidence store with simple locking for concurrent worker writes."""

    def __init__(self, output_dir: str, run_id: str) -> None:
        self.base_path = Path(output_dir) / run_id
        self.workers_path = self.base_path / "workers"
        self.traces_path = self.base_path / "traces"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.workers_path.mkdir(exist_ok=True)
        self.traces_path.mkdir(exist_ok=True)

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        lock_path = path.with_suffix(".lock")
        for _ in range(10):
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                time.sleep(0.1)
        else:
            lock_path.unlink(missing_ok=True)

        try:
            path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        finally:
            lock_path.unlink(missing_ok=True)

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save_manifest(self, manifest: RunManifest) -> None:
        self._write_json(self.base_path / "manifest.json", manifest.model_dump())

    def load_manifest(self) -> RunManifest | None:
        data = self._read_json(self.base_path / "manifest.json")
        return RunManifest(**data) if data else None

    def save_plan(self, plan: TaskPlan) -> None:
        self._write_json(self.base_path / "plan.json", plan.model_dump())

    def load_plan(self) -> TaskPlan | None:
        data = self._read_json(self.base_path / "plan.json")
        return TaskPlan(**data) if data else None

    def save_worker_result(self, result: WorkerResult) -> None:
        filename = f"{result.worker_name}_result.json"
        path = self.workers_path / filename
        existing = self._read_json(path)
        if existing and existing.get("subtask_id") not in (None, result.subtask_id):
            # Same worker ran another subtask this run; keep both results.
            filename = f"{result.worker_name}_{result.subtask_id}_result.json"
            path = self.workers_path / filename
        self._write_json(path, result.model_dump())

    def load_worker_result(self, worker_name: str) -> WorkerResult | None:
        filename = f"{worker_name}_result.json"
        data = self._read_json(self.workers_path / filename)
        return WorkerResult(**data) if data else None

    def load_all_worker_results(self) -> dict[str, WorkerResult]:
        results: dict[str, WorkerResult] = {}
        for path in sorted(self.workers_path.glob("*_result.json")):
            data = self._read_json(path)
            if data:
                result = WorkerResult(**data)
                key = result.worker_name
                if key in results:
                    key = f"{result.worker_name}:{result.subtask_id}"
                results[key] = result
        return results

    def save_final_output(self, output: FinalOutput) -> None:
        self._write_json(self.base_path / "final_output.json", output.model_dump())

    def load_final_output(self) -> FinalOutput | None:
        data = self._read_json(self.base_path / "final_output.json")
        return FinalOutput(**data) if data else None

    def append_trace(self, agent_name: str, entry: dict[str, Any]) -> None:
        path = self.traces_path / f"{agent_name}_trace.jsonl"
        line = json.dumps(entry, default=str) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


class SQLiteEvidenceStore(BaseEvidenceStore):
    """SQLite-based evidence store for better concurrent access and queryability."""

    def __init__(self, output_dir: str, run_id: str) -> None:
        self.base_path = Path(output_dir)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.db_path = self.base_path / "evidence.db"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    def _exec(self, callback):
        """Execute a callback with a connection, ensuring it is closed after."""
        conn = self._connect()
        try:
            result = callback(conn)
            conn.commit()
            return result
        finally:
            conn.close()

    def _init_db(self) -> None:
        def _do(conn):
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS manifests (
                    run_id TEXT PRIMARY KEY, data TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS plans (
                    run_id TEXT PRIMARY KEY, data TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS worker_results (
                    run_id TEXT NOT NULL, worker_name TEXT NOT NULL,
                    data TEXT NOT NULL, status TEXT NOT NULL,
                    findings_count INTEGER DEFAULT 0,
                    recommendations_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (run_id, worker_name)
                );
                CREATE TABLE IF NOT EXISTS final_outputs (
                    run_id TEXT PRIMARY KEY, data TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL, agent_name TEXT NOT NULL,
                    data TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_traces_run_agent ON traces(run_id, agent_name);
                CREATE INDEX IF NOT EXISTS idx_worker_results_run ON worker_results(run_id);
            """)
        self._exec(_do)

    def save_manifest(self, manifest: RunManifest) -> None:
        data = json.dumps(manifest.model_dump(), default=str)
        def _do(conn):
            conn.execute(
                "INSERT INTO manifests (run_id, data) VALUES (?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET data=excluded.data, updated_at=CURRENT_TIMESTAMP",
                (self.run_id, data))
        self._exec(_do)

    def load_manifest(self) -> RunManifest | None:
        def _do(conn):
            return conn.execute("SELECT data FROM manifests WHERE run_id = ?", (self.run_id,)).fetchone()
        row = self._exec(_do)
        return RunManifest(**json.loads(row["data"])) if row else None

    def save_plan(self, plan: TaskPlan) -> None:
        data = json.dumps(plan.model_dump(), default=str)
        def _do(conn):
            conn.execute(
                "INSERT INTO plans (run_id, data) VALUES (?, ?) ON CONFLICT(run_id) DO UPDATE SET data=excluded.data",
                (self.run_id, data))
        self._exec(_do)

    def load_plan(self) -> TaskPlan | None:
        def _do(conn):
            return conn.execute("SELECT data FROM plans WHERE run_id = ?", (self.run_id,)).fetchone()
        row = self._exec(_do)
        return TaskPlan(**json.loads(row["data"])) if row else None

    def save_worker_result(self, result: WorkerResult) -> None:
        data = json.dumps(result.model_dump(), default=str)

        def _select(conn):
            return conn.execute(
                "SELECT data FROM worker_results WHERE run_id = ? AND worker_name = ?",
                (self.run_id, result.worker_name)).fetchone()

        stored_name = result.worker_name
        row = self._exec(_select)
        if row:
            existing_subtask = json.loads(row["data"]).get("subtask_id")
            if existing_subtask not in (None, result.subtask_id):
                # Same worker ran another subtask this run; keep both rows.
                stored_name = f"{result.worker_name}:{result.subtask_id}"

        def _do(conn):
            conn.execute(
                "INSERT INTO worker_results (run_id, worker_name, data, status, findings_count, recommendations_count) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(run_id, worker_name) DO UPDATE SET "
                "data=excluded.data, status=excluded.status, findings_count=excluded.findings_count, "
                "recommendations_count=excluded.recommendations_count",
                (self.run_id, stored_name, data, result.status, len(result.findings), len(result.recommendations)))
        self._exec(_do)

    def load_worker_result(self, worker_name: str) -> WorkerResult | None:
        def _do(conn):
            return conn.execute(
                "SELECT data FROM worker_results WHERE run_id = ? AND worker_name = ?",
                (self.run_id, worker_name)).fetchone()
        row = self._exec(_do)
        return WorkerResult(**json.loads(row["data"])) if row else None

    def load_all_worker_results(self) -> dict[str, WorkerResult]:
        def _do(conn):
            return conn.execute(
                "SELECT worker_name, data FROM worker_results WHERE run_id = ?", (self.run_id,)).fetchall()
        rows = self._exec(_do)
        return {row["worker_name"]: WorkerResult(**json.loads(row["data"])) for row in rows}

    def save_final_output(self, output: FinalOutput) -> None:
        data = json.dumps(output.model_dump(), default=str)
        def _do(conn):
            conn.execute(
                "INSERT INTO final_outputs (run_id, data) VALUES (?, ?) ON CONFLICT(run_id) DO UPDATE SET data=excluded.data",
                (self.run_id, data))
        self._exec(_do)

    def load_final_output(self) -> FinalOutput | None:
        def _do(conn):
            return conn.execute("SELECT data FROM final_outputs WHERE run_id = ?", (self.run_id,)).fetchone()
        row = self._exec(_do)
        return FinalOutput(**json.loads(row["data"])) if row else None

    def append_trace(self, agent_name: str, entry: dict[str, Any]) -> None:
        data = json.dumps(entry, default=str)
        def _do(conn):
            conn.execute("INSERT INTO traces (run_id, agent_name, data) VALUES (?, ?, ?)",
                         (self.run_id, agent_name, data))
        self._exec(_do)

    def load_traces(self, agent_name: str | None = None) -> list[dict[str, Any]]:
        def _do(conn):
            if agent_name:
                return conn.execute(
                    "SELECT agent_name, data, created_at FROM traces WHERE run_id = ? AND agent_name = ? ORDER BY id",
                    (self.run_id, agent_name)).fetchall()
            return conn.execute(
                "SELECT agent_name, data, created_at FROM traces WHERE run_id = ? ORDER BY id",
                (self.run_id,)).fetchall()
        rows = self._exec(_do)
        return [{"agent": r["agent_name"], "ts": r["created_at"], **json.loads(r["data"])} for r in rows]

    def list_runs(self) -> list[dict[str, Any]]:
        def _do(conn):
            return conn.execute("SELECT run_id, data, created_at FROM manifests ORDER BY created_at DESC").fetchall()
        rows = self._exec(_do)
        return [{"run_id": r["run_id"], "created_at": r["created_at"], **json.loads(r["data"])} for r in rows]

    def get_run_summary(self) -> dict[str, Any] | None:
        def _do(conn):
            return conn.execute(
                "SELECT worker_name, status, findings_count, recommendations_count FROM worker_results WHERE run_id = ?",
                (self.run_id,)).fetchall()
        rows = self._exec(_do)
        if not rows:
            return None
        return {
            "run_id": self.run_id,
            "workers": [{"name": r["worker_name"], "status": r["status"],
                         "findings": r["findings_count"], "recommendations": r["recommendations_count"]} for r in rows],
        }


def create_evidence_store(
    output_dir: str,
    run_id: str,
    backend: str = "file",
) -> BaseEvidenceStore:
    """Factory function for creating evidence stores.

    Args:
        output_dir: Directory for output files/database
        run_id: Unique run identifier
        backend: "file" for JSON files, "sqlite" for SQLite database
    """
    if backend == "sqlite":
        return SQLiteEvidenceStore(output_dir, run_id)
    return EvidenceStore(output_dir, run_id)
