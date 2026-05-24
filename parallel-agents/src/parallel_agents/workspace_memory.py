from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEMORY_DIR_NAME = "memory"
MEMORY_KINDS = {"decision", "lesson"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _memory_dir(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / MEMORY_DIR_NAME


def _memory_file(project_root: str | Path, kind: str) -> Path:
    if kind not in MEMORY_KINDS:
        raise ValueError(f"Unsupported memory kind: {kind}")
    filename = "decisions.jsonl" if kind == "decision" else "lessons.jsonl"
    return _memory_dir(project_root) / filename


def _memory_policy_path(project_root: str | Path) -> Path:
    return _memory_dir(project_root) / "policies.json"


def ensure_workspace_memory(project_root: str | Path) -> dict[str, str]:
    root = Path(project_root).resolve()
    memory_root = _memory_dir(root)
    memory_root.mkdir(parents=True, exist_ok=True)

    decision_path = _memory_file(root, "decision")
    lesson_path = _memory_file(root, "lesson")
    for path in (decision_path, lesson_path):
        if not path.exists():
            path.write_text("", encoding="utf-8")

    policy_path = _memory_policy_path(root)
    if not policy_path.exists():
        default_policy = {
            "schema_version": 1,
            "updated_at": _utc_now(),
            "rules": [],
        }
        policy_path.write_text(json.dumps(default_policy, indent=2), encoding="utf-8")

    return {
        "memory_dir": str(memory_root),
        "decisions_file": str(decision_path),
        "lessons_file": str(lesson_path),
        "policies_file": str(policy_path),
    }


def add_memory_entry(
    project_root: str | Path,
    *,
    kind: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    owner_role: str | None = None,
    source: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    normalized_kind = str(kind).strip().lower()
    if normalized_kind not in MEMORY_KINDS:
        raise ValueError(f"kind must be one of: {', '.join(sorted(MEMORY_KINDS))}")

    normalized_title = str(title).strip()
    if not normalized_title:
        raise ValueError("title is required")
    normalized_content = str(content).strip()
    if not normalized_content:
        raise ValueError("content is required")

    ensure_workspace_memory(project_root)
    entry = {
        "id": f"mem-{uuid.uuid4().hex[:12]}",
        "kind": normalized_kind,
        "created_at": _utc_now(),
        "title": normalized_title,
        "content": normalized_content,
        "tags": [str(tag).strip() for tag in (tags or []) if str(tag).strip()],
        "owner_role": (str(owner_role).strip() if owner_role else None),
        "source": (str(source).strip() if source else None),
        "run_id": (str(run_id).strip() if run_id else None),
    }

    path = _memory_file(project_root, normalized_kind)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, default=str) + "\n")
    return entry


def list_memory_entries(
    project_root: str | Path,
    *,
    kind: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    ensure_workspace_memory(project_root)
    selected: list[str]
    if kind:
        normalized_kind = str(kind).strip().lower()
        if normalized_kind not in MEMORY_KINDS:
            raise ValueError(f"kind must be one of: {', '.join(sorted(MEMORY_KINDS))}")
        selected = [normalized_kind]
    else:
        selected = sorted(MEMORY_KINDS)

    entries: list[dict[str, Any]] = []
    for item_kind in selected:
        path = _memory_file(project_root, item_kind)
        entries.extend(_load_jsonl(path))

    entries.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return entries[: max(1, int(limit))]


def search_memory_entries(
    project_root: str | Path,
    *,
    query: str,
    kind: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    text = str(query).strip().lower()
    if not text:
        raise ValueError("query is required")

    entries = list_memory_entries(project_root, kind=kind, limit=10_000)
    matches: list[dict[str, Any]] = []
    for entry in entries:
        searchable = " ".join(
            [
                str(entry.get("title", "")),
                str(entry.get("content", "")),
                " ".join(str(tag) for tag in (entry.get("tags") or [])),
                str(entry.get("owner_role") or ""),
                str(entry.get("source") or ""),
                str(entry.get("run_id") or ""),
            ]
        ).lower()
        if text in searchable:
            matches.append(entry)
        if len(matches) >= max(1, int(limit)):
            break
    return matches


def load_memory_policies(project_root: str | Path) -> dict[str, Any]:
    ensure_workspace_memory(project_root)
    path = _memory_policy_path(project_root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("memory policy file must be a JSON object")
    return payload


def save_memory_policies(project_root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("policy payload must be a JSON object")
    ensure_workspace_memory(project_root)
    merged = dict(payload)
    merged["updated_at"] = _utc_now()
    merged.setdefault("schema_version", 1)
    path = _memory_policy_path(project_root)
    path.write_text(json.dumps(merged, indent=2, default=str), encoding="utf-8")
    return merged


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not path.exists():
        return items
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items
