"""Unit tests for data models — serialization, validation, defaults."""

from __future__ import annotations

import json

from parallel_agents.models import (
    Finding,
    FinalOutput,
    GitHubIssueContext,
    InputType,
    Priority,
    Recommendation,
    RecommendationType,
    RunManifest,
    Severity,
    Subtask,
    TaskInput,
    TaskPlan,
    TaskStatus,
    WorkerResult,
)


class TestTaskInput:
    def test_create_free_text(self):
        ti = TaskInput(raw_input="fix the bug", input_type=InputType.FREE_TEXT)
        assert ti.raw_input == "fix the bug"
        assert ti.input_type == InputType.FREE_TEXT
        assert ti.repo_path is None

    def test_create_github_issue(self):
        ti = TaskInput(
            raw_input="https://github.com/org/repo/issues/42",
            input_type=InputType.GITHUB_ISSUE,
            github_url="https://github.com/org/repo/issues/42",
            github_issue=GitHubIssueContext(
                number=42,
                title="Bug report",
                body="Please fix this",
            ),
        )
        assert ti.input_type == InputType.GITHUB_ISSUE
        assert ti.github_url is not None
        assert ti.github_issue is not None

    def test_serialization_roundtrip(self):
        ti = TaskInput(raw_input="test", input_type=InputType.REPO_PATH, repo_path="/tmp/repo")
        data = ti.model_dump()
        restored = TaskInput(**data)
        assert restored == ti


class TestSubtask:
    def test_defaults(self):
        s = Subtask(id="s1", description="test", assigned_worker="security")
        assert s.context == {}
        assert s.dependencies == []
        assert s.priority == 0

    def test_with_dependencies(self):
        s = Subtask(
            id="s2", description="review", assigned_worker="review",
            dependencies=["s1"], priority=5,
        )
        assert s.dependencies == ["s1"]
        assert s.priority == 5


class TestTaskPlan:
    def test_empty_plan(self):
        plan = TaskPlan(summary="empty")
        assert plan.subtasks == []
        assert plan.repo_analysis == {}

    def test_with_subtasks(self):
        plan = TaskPlan(
            summary="test plan",
            subtasks=[
                Subtask(id="s1", description="scan", assigned_worker="security"),
                Subtask(id="s2", description="code", assigned_worker="code"),
            ],
            repo_analysis={"languages": ["python"]},
        )
        assert len(plan.subtasks) == 2


class TestFinding:
    def test_minimal(self):
        f = Finding(severity=Severity.HIGH, category="vuln", title="SQLi", description="found sqli")
        assert f.severity == Severity.HIGH
        assert f.file_path is None

    def test_full(self):
        f = Finding(
            severity=Severity.CRITICAL, category="auth", title="Broken Auth",
            description="no auth check", file_path="src/api.py",
            line_range=(10, 20), evidence="if True: pass",
        )
        assert f.line_range == (10, 20)


class TestRecommendation:
    def test_defaults(self):
        r = Recommendation(type=RecommendationType.CODE_CHANGE, description="fix it")
        assert r.priority == Priority.SHOULD
        assert r.rationale == ""

    def test_full(self):
        r = Recommendation(
            type=RecommendationType.CONFIG_CHANGE, description="update config",
            file_path=".env", suggested_content="DEBUG=false",
            rationale="security", priority=Priority.MUST,
        )
        assert r.priority == Priority.MUST


class TestWorkerResult:
    def test_defaults(self):
        r = WorkerResult(worker_name="security", subtask_id="s1")
        assert r.status == "success"
        assert r.findings == []
        assert r.recommendations == []
        assert r.cost_usd == 0.0

    def test_json_roundtrip(self):
        r = WorkerResult(
            worker_name="code", subtask_id="s2",
            findings=[Finding(severity=Severity.LOW, category="style", title="naming", description="bad name")],
        )
        data = json.loads(r.model_dump_json())
        restored = WorkerResult(**data)
        assert len(restored.findings) == 1
        assert restored.findings[0].title == "naming"


class TestFinalOutput:
    def test_empty(self):
        out = FinalOutput(summary="nothing found")
        assert out.patch is None
        assert out.risk_report == []

    def test_with_data(self):
        out = FinalOutput(
            summary="analysis complete",
            risk_report=[Finding(severity=Severity.HIGH, category="sec", title="XSS", description="xss found")],
            patch="--- a/file.py\n+++ b/file.py\n@@ ...",
            pr_summary="Fixed XSS vulnerability",
        )
        assert out.patch is not None
        assert len(out.risk_report) == 1


class TestRunManifest:
    def test_defaults(self):
        m = RunManifest(
            run_id="abc123",
            input=TaskInput(raw_input="test", input_type=InputType.FREE_TEXT),
        )
        assert m.status == TaskStatus.PENDING
        assert m.total_tokens == 0
