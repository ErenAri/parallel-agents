"""Per-user MRU history for free-text inputs (repo paths, owner/repo refs).

Persisted to ~/.parallel-agents-desktop-history.json. Keys are arbitrary
strings, values are ordered most-recent-first with case-preserving de-dup
and a per-key cap.
"""

from __future__ import annotations

import json
from pathlib import Path

HISTORY_FILENAME = ".parallel-agents-desktop-history.json"
DEFAULT_LIMIT = 8


class HistoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (Path.home() / HISTORY_FILENAME)

    def get(self, key: str, limit: int = DEFAULT_LIMIT) -> list[str]:
        data = self._read()
        values = data.get(key, [])
        if not isinstance(values, list):
            return []
        cleaned = [str(v) for v in values if v]
        return cleaned[:limit]

    def add(self, key: str, value: str, limit: int = DEFAULT_LIMIT) -> list[str]:
        value = (value or "").strip()
        if not value:
            return self.get(key, limit=limit)
        data = self._read()
        existing = data.get(key, [])
        if not isinstance(existing, list):
            existing = []
        # de-dup while preserving insertion order, value at front
        deduped: list[str] = [value]
        for item in existing:
            s = str(item)
            if s and s != value and s not in deduped:
                deduped.append(s)
            if len(deduped) >= limit:
                break
        data[key] = deduped
        self._write(data)
        return deduped

    def clear(self, key: str) -> None:
        data = self._read()
        if key in data:
            data.pop(key)
            self._write(data)

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
