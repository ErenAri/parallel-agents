from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


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
    max_parallel_workers: int = 4
    output_dir: str = ".parallel-agents-output"
    max_retries: int = 2
    retry_delay_seconds: float = 5.0
    store_backend: str = "file"  # "file" or "sqlite"

    model_config = {"env_prefix": "PA_", "env_file": ".env"}
