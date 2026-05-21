from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CompanyArtifactIndex(BaseModel):
    run_id: str
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    artifacts: dict[str, str] = Field(default_factory=dict)


def persist_company_artifact(
    output_dir: str | Path,
    run_id: str,
    artifact_name: str,
    artifact_payload: BaseModel | dict[str, Any],
) -> Path:
    """Persist a company artifact under .parallel-agents-output/<run_id>/company."""
    if not run_id.strip():
        raise ValueError("run_id cannot be empty")
    if not artifact_name.strip():
        raise ValueError("artifact_name cannot be empty")

    base = Path(output_dir) / run_id / "company"
    base.mkdir(parents=True, exist_ok=True)

    file_path = base / f"{artifact_name}.json"
    payload = _to_payload_dict(artifact_payload)
    file_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    index = load_company_artifact_index(output_dir, run_id) or CompanyArtifactIndex(run_id=run_id)
    index.artifacts[artifact_name] = file_path.name
    index.updated_at = _utc_now()
    (base / "index.json").write_text(index.model_dump_json(indent=2), encoding="utf-8")
    return file_path


def load_company_artifact_index(output_dir: str | Path, run_id: str) -> CompanyArtifactIndex | None:
    path = Path(output_dir) / run_id / "company" / "index.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return CompanyArtifactIndex.model_validate(payload)


def list_company_artifact_paths(output_dir: str | Path, run_id: str) -> dict[str, str]:
    index = load_company_artifact_index(output_dir, run_id)
    if not index:
        return {}
    base = Path(output_dir) / run_id / "company"
    return {name: str((base / rel_path).resolve()) for name, rel_path in index.artifacts.items()}


def load_company_artifact(
    output_dir: str | Path,
    run_id: str,
    artifact_name: str,
) -> dict[str, Any] | None:
    """Load one named artifact from a run-linked company artifact directory."""
    paths = list_company_artifact_paths(output_dir, run_id)
    artifact_path = paths.get(artifact_name)
    if not artifact_path:
        return None
    path = Path(artifact_path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def append_company_artifact_event(
    output_dir: str | Path,
    run_id: str,
    artifact_name: str,
    event_payload: BaseModel | dict[str, Any],
) -> Path:
    """Append an immutable event record for a company artifact."""
    if not run_id.strip():
        raise ValueError("run_id cannot be empty")
    if not artifact_name.strip():
        raise ValueError("artifact_name cannot be empty")

    base = Path(output_dir) / run_id / "company"
    audit_dir = base / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    log_path = audit_dir / f"{artifact_name}.jsonl"
    payload = _to_payload_dict(event_payload)
    previous_hash = _load_last_event_hash(log_path)

    body = {
        "payload": payload,
        "previous_hash": previous_hash,
    }
    body_json = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    entry_hash = hashlib.sha256(body_json.encode("utf-8")).hexdigest()

    entry = {
        "timestamp": _utc_now().isoformat(),
        "hash": entry_hash,
        "previous_hash": previous_hash,
        "payload": payload,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, default=str))
        handle.write("\n")

    index = load_company_artifact_index(output_dir, run_id) or CompanyArtifactIndex(run_id=run_id)
    index.artifacts[f"{artifact_name}-audit-log"] = str(Path("audit") / log_path.name)
    index.updated_at = _utc_now()
    (base / "index.json").write_text(index.model_dump_json(indent=2), encoding="utf-8")
    return log_path


def load_company_artifact_events(
    output_dir: str | Path,
    run_id: str,
    artifact_name: str,
) -> list[dict[str, Any]]:
    """Load append-only event records for a company artifact."""
    log_path = Path(output_dir) / run_id / "company" / "audit" / f"{artifact_name}.jsonl"
    if not log_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    return events


def _load_last_event_hash(log_path: Path) -> str | None:
    if not log_path.exists():
        return None
    last_hash: str | None = None
    for line in log_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        value = entry.get("hash")
        if isinstance(value, str) and value:
            last_hash = value
    return last_hash


def _to_payload_dict(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value
