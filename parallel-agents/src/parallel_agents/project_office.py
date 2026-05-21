from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OFFICE_DIR_NAME = ".parallel-agents"
PROJECT_FILE_NAME = "project.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_project_root(path: str | Path | None = None) -> Path:
    return Path(path or ".").resolve()


def office_dir(project_root: str | Path | None = None) -> Path:
    return resolve_project_root(project_root) / OFFICE_DIR_NAME


def office_output_dir(project_root: str | Path | None = None) -> Path:
    """Return the default output root for office workflows."""
    return office_dir(project_root)


def init_project_office(
    project_root: str | Path | None = None,
    *,
    name: str | None = None,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    root.mkdir(parents=True, exist_ok=True)
    base = office_dir(root)
    base.mkdir(parents=True, exist_ok=True)

    for child in ("runs", "artifacts", "approvals", "audit", "metrics"):
        (base / child).mkdir(exist_ok=True)

    project_file = base / PROJECT_FILE_NAME
    existing = load_project_office(root)
    now = utc_now()
    payload = {
        "schema_version": 1,
        "name": name or existing.get("name") or root.name,
        "project_root": str(root),
        "office_dir": str(base),
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "output_dir": str(base),
        "mode": "local-project-office",
    }
    project_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def list_office_run_ids(project_root: str | Path | None = None) -> list[str]:
    """List run ids that contain company artifacts in the office workspace."""
    output_root = office_output_dir(project_root)
    if not output_root.exists():
        return []

    run_ids: list[str] = []
    for child in output_root.iterdir():
        if not child.is_dir():
            continue
        if (child / "company" / "index.json").exists():
            run_ids.append(child.name)
    return sorted(run_ids, reverse=True)


def load_project_office(project_root: str | Path | None = None) -> dict[str, Any]:
    project_file = office_dir(project_root) / PROJECT_FILE_NAME
    if not project_file.exists():
        return {}
    payload = json.loads(project_file.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def get_project_office_status(project_root: str | Path | None = None) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    base = office_dir(root)
    project = load_project_office(root)
    dirs = {
        "runs": base / "runs",
        "artifacts": base / "artifacts",
        "approvals": base / "approvals",
        "audit": base / "audit",
        "metrics": base / "metrics",
    }
    return {
        "initialized": bool(project),
        "project_root": str(root),
        "office_dir": str(base),
        "project": project,
        "directories": {name: str(path) for name, path in dirs.items()},
        "directory_exists": {name: path.exists() for name, path in dirs.items()},
        "gateway_db": str(base / "gateway.sqlite"),
        "gateway_db_exists": (base / "gateway.sqlite").exists(),
    }
