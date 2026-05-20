from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class InputType(str, Enum):
    GITHUB_ISSUE = "github_issue"
    REPO_PATH = "repo_path"
    FREE_TEXT = "free_text"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class RecommendationType(str, Enum):
    CODE_CHANGE = "code_change"
    CONFIG_CHANGE = "config_change"
    PROCESS = "process"
    DOCUMENTATION = "documentation"


class Priority(str, Enum):
    MUST = "must"
    SHOULD = "should"
    COULD = "could"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GitHubIssueContext(BaseModel):
    number: int
    title: str
    body: str
    labels: list[str] = Field(default_factory=list)
    state: str = ""
    url: str = ""
    comments: list[dict[str, str]] = Field(default_factory=list)


class TaskInput(BaseModel):
    raw_input: str
    input_type: InputType
    repo_path: str | None = None
    github_url: str | None = None
    github_issue: GitHubIssueContext | None = None


class Subtask(BaseModel):
    id: str
    description: str
    assigned_worker: str
    context: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    priority: int = 0


class TaskPlan(BaseModel):
    summary: str
    repo_analysis: dict[str, Any] = Field(default_factory=dict)
    subtasks: list[Subtask] = Field(default_factory=list)
    global_context: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    severity: Severity
    category: str
    title: str
    description: str
    file_path: str | None = None
    line_range: tuple[int, int] | None = None
    evidence: str | None = None


class Recommendation(BaseModel):
    type: RecommendationType
    description: str
    file_path: str | None = None
    suggested_content: str | None = None
    rationale: str = ""
    priority: Priority = Priority.SHOULD


class WorkerResult(BaseModel):
    worker_name: str
    subtask_id: str
    status: str = "success"
    findings: list[Finding] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    raw_output: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    token_usage: dict[str, int] | None = None
    cost_usd: float = 0.0


class FinalOutput(BaseModel):
    summary: str
    risk_report: list[Finding] = Field(default_factory=list)
    patch: str | None = None
    pr_summary: str = ""
    worker_results: dict[str, WorkerResult] = Field(default_factory=dict)
    conflicts_resolved: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunManifest(BaseModel):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    input: TaskInput
    status: TaskStatus = TaskStatus.PENDING
    phases: dict[str, dict[str, Any]] = Field(default_factory=dict)
    workers_invoked: list[str] = Field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0
