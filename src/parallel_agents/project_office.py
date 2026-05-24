from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from parallel_agents.workspace_memory import ensure_workspace_memory

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

    for child in ("runs", "artifacts", "approvals", "audit", "metrics", "memory"):
        (base / child).mkdir(exist_ok=True)
    ensure_workspace_memory(base)

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
        "memory": base / "memory",
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


def run_office_diagnostics(project_root: str | Path | None = None) -> dict[str, Any]:
    """Run local project-office diagnostics for desktop and CLI surfaces."""
    status = get_project_office_status(project_root)
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "name": "project-root",
            "status": "passed" if Path(status["project_root"]).exists() else "failed",
            "detail": status["project_root"],
        }
    )

    office_initialized = bool(status.get("initialized"))
    checks.append(
        {
            "name": "office-initialized",
            "status": "passed" if office_initialized else "failed",
            "detail": "initialized" if office_initialized else "run `parallel-agents office init`",
        }
    )

    if office_initialized:
        missing_dirs = [
            name
            for name, exists in (status.get("directory_exists") or {}).items()
            if not bool(exists)
        ]
        checks.append(
            {
                "name": "workspace-directories",
                "status": "passed" if not missing_dirs else "failed",
                "detail": "all present" if not missing_dirs else f"missing: {', '.join(sorted(missing_dirs))}",
            }
        )
    else:
        checks.append(
            {
                "name": "workspace-directories",
                "status": "warning",
                "detail": "skipped (office not initialized)",
            }
        )

    checks.extend(
        [
            _tool_check("git", required=True, description="required for repository operations"),
            _tool_check("gh", required=False, description="optional for GitHub issue/PR operations"),
            _tool_check("npm", required=False, description="optional for npm wrapper release checks"),
            _tool_check("claude", required=False, description="optional for Claude CLI runtime flows"),
        ]
    )

    passed_checks = sum(1 for item in checks if item["status"] == "passed")
    warning_checks = sum(1 for item in checks if item["status"] == "warning")
    failed_checks = sum(1 for item in checks if item["status"] == "failed")
    healthy = failed_checks == 0 and warning_checks == 0
    return {
        "project_root": status["project_root"],
        "office_dir": status["office_dir"],
        "office_initialized": office_initialized,
        "passed_checks": passed_checks,
        "warning_checks": warning_checks,
        "failed_checks": failed_checks,
        "healthy": healthy,
        "checks": checks,
    }


def suggest_office_setup_commands(diagnostics: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    for check in diagnostics.get("checks", []):
        if not isinstance(check, dict):
            continue
        if str(check.get("status")) not in {"failed", "warning"}:
            continue
        name = str(check.get("name", ""))
        if name == "tool:gh":
            suggestions.append("gh auth login")
        elif name == "tool:npm":
            suggestions.append("npm --version")
        elif name == "tool:claude":
            suggestions.append("claude --version")
        elif name == "office-initialized":
            suggestions.append("parallel-agents office init --project .")

    ordered: list[str] = []
    for command in suggestions:
        if command not in ordered:
            ordered.append(command)
    return ordered


def run_office_setup_fix(project_root: str | Path | None = None) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    before = run_office_diagnostics(root)
    actions: list[str] = []
    if not bool(before.get("office_initialized")):
        init_project_office(root, name=root.name)
        actions.append("initialized_office_workspace")
    after = run_office_diagnostics(root)
    return {
        "project_root": str(root),
        "before": before,
        "after": after,
        "actions_taken": actions,
        "suggested_commands": suggest_office_setup_commands(after),
    }


def _tool_check(tool_name: str, *, required: bool, description: str) -> dict[str, Any]:
    path = shutil.which(tool_name)
    if path:
        return {
            "name": f"tool:{tool_name}",
            "status": "passed",
            "detail": path,
            "required": required,
            "description": description,
        }
    return {
        "name": f"tool:{tool_name}",
        "status": "failed" if required else "warning",
        "detail": "not found in PATH",
        "required": required,
        "description": description,
    }
