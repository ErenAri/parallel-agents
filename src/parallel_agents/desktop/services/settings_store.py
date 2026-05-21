"""Settings persistence for the desktop app.

Two scopes, project overrides user:
  - user:    ~/.parallel-agents-desktop.json   (machine-wide defaults)
  - project: <root>/.parallel-agents/desktop.json

On launch, both files are loaded (project last) and applied to os.environ so
the rest of the engine picks up PA_* values without further plumbing.

Only a known allow-list of keys is read/written so a malformed file can't
inject arbitrary env vars.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

USER_SETTINGS_FILENAME = ".parallel-agents-desktop.json"
PROJECT_SETTINGS_FILENAME = "desktop.json"

# Allow-listed env vars. Order matters only for documentation.
KNOWN_KEYS: tuple[str, ...] = (
    "PA_PLANNER_MODEL",
    "PA_JUDGE_MODEL",
    "PA_PERMISSION_MODE",
    "PA_GATEWAY_API_KEY",
    "PA_DESKTOP_LLM_BRIEF",
    "PA_DESKTOP_LLM_PRFAQ",
    "PA_DESKTOP_LLM_RFC",
    "PA_DESKTOP_LLM_MODEL",
    "PA_DESKTOP_BRIEF_MODEL",
)


@dataclass
class LoadedSettings:
    user: dict[str, str]
    project: dict[str, str]
    effective: dict[str, str]  # what was written to os.environ this load


class SettingsStore:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root

    # -- paths ---------------------------------------------------------

    @staticmethod
    def user_path() -> Path:
        return Path.home() / USER_SETTINGS_FILENAME

    def project_path(self) -> Path | None:
        if self.project_root is None:
            return None
        return self.project_root / ".parallel-agents" / PROJECT_SETTINGS_FILENAME

    # -- read ----------------------------------------------------------

    def load(self) -> LoadedSettings:
        user = _read_filtered(self.user_path())
        project_path = self.project_path()
        project = _read_filtered(project_path) if project_path else {}
        effective = {**user, **project}  # project wins
        for key, value in effective.items():
            os.environ[key] = value
        return LoadedSettings(user=user, project=project, effective=effective)

    # -- write ---------------------------------------------------------

    def save_user(self, values: dict[str, str]) -> Path:
        return _write_filtered(self.user_path(), values)

    def save_project(self, values: dict[str, str]) -> Path:
        project_path = self.project_path()
        if project_path is None:
            raise RuntimeError("No project root configured for settings save.")
        return _write_filtered(project_path, values)


def _read_filtered(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: str(v) for k, v in raw.items() if k in KNOWN_KEYS and v not in (None, "")}


def _write_filtered(path: Path, values: dict[str, str]) -> Path:
    cleaned = {k: str(v) for k, v in values.items() if k in KNOWN_KEYS and v not in (None, "")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    return path
