from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# Single source of truth for the workspace root. The desktop office, the CLI,
# the gateway, and the MCP server all default to this one directory so they
# operate on the same workspace instead of diverging into two trees.
DEFAULT_ARTIFACT_DIR = ".parallel-agents"
# Pre-unification CLI/gateway/MCP default. A one-time `office migrate` moves a
# legacy workspace onto the unified root; see migrate_legacy_artifact_dir.
LEGACY_ARTIFACT_DIR = ".parallel-agents-output"


def migrate_legacy_artifact_dir(project_root: str | Path = ".") -> dict[str, object]:
    """Move a legacy ``.parallel-agents-output`` workspace onto the unified root.

    Explicit and safe by design (no implicit, intent-blind fallback that could
    silently split a project across two roots): it only acts when the legacy
    directory exists and the unified ``.parallel-agents`` directory does not, and
    it never merges or overwrites. Returns a small report describing the outcome.
    """
    root = Path(project_root)
    legacy = root / LEGACY_ARTIFACT_DIR
    target = root / DEFAULT_ARTIFACT_DIR
    if not legacy.exists():
        return {"migrated": False, "reason": "no-legacy-dir", "legacy": str(legacy)}
    if target.exists():
        return {
            "migrated": False,
            "reason": "target-exists",
            "legacy": str(legacy),
            "target": str(target),
        }
    legacy.rename(target)
    return {"migrated": True, "legacy": str(legacy), "target": str(target)}


class WorkerConfig(BaseModel):
    enabled: bool = True
    model: str = "sonnet"
    max_turns: int = 15
    timeout_seconds: int = 300


class PipelineConfig(BaseSettings):
    anthropic_api_key: str | None = None

    workers: dict[str, WorkerConfig] = Field(default_factory=lambda: {
        "security": WorkerConfig(),
        "test": WorkerConfig(),
        "perf": WorkerConfig(),
        "devops": WorkerConfig(),
        "arch": WorkerConfig(),
        "docs": WorkerConfig(),
        "code": WorkerConfig(model="opus"),
        "review": WorkerConfig(),
    })

    planner_model: str = "opus"
    judge_model: str = "opus"
    permission_mode: Literal["default", "acceptEdits", "plan", "bypassPermissions"] = "default"
    max_parallel_workers: int = 4
    output_dir: str = DEFAULT_ARTIFACT_DIR
    max_retries: int = 2
    retry_delay_seconds: float = 5.0
    parse_retry_attempts: int = 1
    store_backend: str = "file"  # "file" or "sqlite"

    model_config = {"env_prefix": "PA_", "env_file": ".env"}
