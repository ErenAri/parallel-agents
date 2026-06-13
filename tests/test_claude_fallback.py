"""Tests for SDK->CLI fallback behavior."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from parallel_agents.agents.judge import run_judge
from parallel_agents.agents.planner import run_planner
from parallel_agents.agents.workers.review import ReviewWorker
from parallel_agents.claude_cli_fallback import _parse_stream_json_output
from parallel_agents.claude_cli_fallback import _build_cli_command
from parallel_agents.claude_cli_fallback import _is_missing_print_input_error
from parallel_agents.claude_cli_fallback import _resolve_windows_claude_executable
from parallel_agents.claude_cli_fallback import _with_inlined_system_prompt
from parallel_agents.config import PipelineConfig, WorkerConfig
from parallel_agents.models import (
    RecommendationType,
    Subtask,
    TaskInput,
    TaskPlan,
    WorkerResult,
    InputType,
)


def _planner_json() -> str:
    return json.dumps(
        {
            "summary": "Fallback planner response",
            "repo_analysis": {"languages": ["python"]},
            "subtasks": [
                {
                    "id": "s1",
                    "description": "Review code",
                    "assigned_worker": "review",
                    "context": {},
                    "dependencies": [],
                    "priority": 1,
                }
            ],
            "global_context": {},
        }
    )


def _worker_json() -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "severity": "medium",
                    "category": "style",
                    "title": "Naming issue",
                    "description": "Rename variable for readability",
                    "file_path": "src/main.py",
                }
            ],
            "recommendations": [
                {
                    "type": "code_change",
                    "description": "Rename variable",
                    "file_path": "src/main.py",
                    "suggested_content": "new_name = old_name",
                    "rationale": "clear naming",
                    "priority": "should",
                }
            ],
        }
    )


def _judge_json() -> str:
    return json.dumps(
        {
            "summary": "Judge merged fallback responses",
            "risk_report": [],
            "patch": None,
            "pr_summary": "No patch required",
            "conflicts_resolved": [],
        }
    )


@pytest.mark.asyncio
async def test_planner_uses_cli_fallback_when_sdk_fails():
    config = PipelineConfig()
    task_input = TaskInput(raw_input="review", input_type=InputType.FREE_TEXT, repo_path=".")

    def failing_query(*, prompt, options=None):
        raise RuntimeError("sdk parse failure")

    with patch("parallel_agents.agents.planner.query", new=failing_query):
        with patch(
            "parallel_agents.agents.planner.run_query_via_cli",
            new=AsyncMock(
                return_value=(
                    _planner_json(),
                    0.02,
                    {"input_tokens": 100, "output_tokens": 50},
                )
            ),
        ):
            plan = await run_planner(task_input, config)

    assert plan.summary == "Fallback planner response"
    metrics = plan.global_context["planner_metrics"]
    assert metrics["token_usage"]["fallback_cli_used"] == 1


@pytest.mark.asyncio
async def test_worker_uses_cli_fallback_when_sdk_fails():
    worker = ReviewWorker(WorkerConfig(enabled=True))
    subtask = Subtask(id="s1", description="review", assigned_worker="review")
    plan = TaskPlan(
        summary="plan",
        repo_analysis={"languages": ["python"]},
        subtasks=[subtask],
        global_context={"repo_path": ".", "permission_mode": "default"},
    )

    def failing_query(*, prompt, options=None):
        raise RuntimeError("sdk parse failure")

    with patch("parallel_agents.agents.base.query", new=failing_query):
        with patch(
            "parallel_agents.agents.base.run_query_via_cli",
            new=AsyncMock(
                return_value=(
                    _worker_json(),
                    0.01,
                    {"input_tokens": 10, "output_tokens": 5},
                )
            ),
        ):
            result = await worker.execute(subtask, plan)

    assert result.status == "success"
    assert len(result.findings) == 1
    assert len(result.recommendations) == 1
    assert result.recommendations[0].type == RecommendationType.CODE_CHANGE
    assert result.token_usage and result.token_usage["fallback_cli_used"] == 1


@pytest.mark.asyncio
async def test_judge_uses_cli_fallback_when_sdk_fails():
    config = PipelineConfig()
    plan = TaskPlan(summary="plan", repo_analysis={}, subtasks=[], global_context={"repo_path": "."})
    worker_results = {
        "review": WorkerResult(worker_name="review", subtask_id="s1"),
    }

    def failing_query(*, prompt, options=None):
        raise RuntimeError("sdk parse failure")

    with patch("parallel_agents.agents.judge.query", new=failing_query):
        with patch(
            "parallel_agents.agents.judge.run_query_via_cli",
            new=AsyncMock(
                return_value=(
                    _judge_json(),
                    0.01,
                    {"input_tokens": 20, "output_tokens": 10},
                )
            ),
        ):
            result = await run_judge(plan, worker_results, config)

    assert result.summary == "Judge merged fallback responses"
    assert result.metadata["token_usage"]["fallback_cli_used"] == 1


def test_parse_stream_json_output_ignores_unknown_events():
    output = "\n".join(
        [
            json.dumps({"type": "system", "subtype": "init"}),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "hello"}]},
                }
            ),
            json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}}),
            json.dumps(
                {
                    "type": "result",
                    "total_cost_usd": 0.5,
                    "result": "hello",
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                }
            ),
        ]
    )
    text, cost, usage = _parse_stream_json_output(output)
    assert text == "hello"
    assert cost == 0.5
    assert usage["input_tokens"] == 3
    assert usage["output_tokens"] == 2


def test_build_cli_command_uses_print_without_positional_prompt():
    from claude_code_sdk import ClaudeCodeOptions

    options = ClaudeCodeOptions(
        system_prompt="Line1\n- item",
        append_system_prompt="Extra",
        model="haiku",
        permission_mode="default",
    )
    cmd = _build_cli_command("claude", options)
    cmd_text = " ".join(cmd)
    # System prompts are inlined into the stdin prompt, never passed as flags.
    assert "--system-prompt" not in cmd_text
    assert "--append-system-prompt" not in cmd_text
    # The prompt is delivered via stdin, so the command ends at --print with
    # no end-of-options separator and no positional prompt argument.
    assert cmd[-1] == "--print"
    assert "--" not in cmd


def test_build_cli_command_can_include_positional_prompt_for_retry():
    from claude_code_sdk import ClaudeCodeOptions

    options = ClaudeCodeOptions(model="haiku")
    cmd = _build_cli_command("claude", options, positional_prompt="hello")

    assert cmd[-2:] == ["--print", "hello"]


def test_missing_print_input_error_detection():
    assert _is_missing_print_input_error(
        "Error: Input must be provided either through stdin or as a prompt argument when using --print"
    )
    assert not _is_missing_print_input_error("some other error")


def test_resolve_windows_claude_executable_prefers_real_exe(tmp_path):
    npm_dir = tmp_path / "npm"
    cli_dir = npm_dir / "node_modules" / "@anthropic-ai" / "claude-code" / "bin"
    cli_dir.mkdir(parents=True)
    cmd_shim = npm_dir / "claude.cmd"
    cmd_shim.write_text("@echo off\n", encoding="utf-8")
    real_exe = cli_dir / "claude.exe"
    real_exe.write_text("", encoding="utf-8")

    assert _resolve_windows_claude_executable(cmd_shim, is_windows=True) == real_exe


def test_inlined_system_prompt_merges_system_and_user():
    from claude_code_sdk import ClaudeCodeOptions

    options = ClaudeCodeOptions(
        system_prompt="Line1\n- item",
        append_system_prompt="Extra",
    )
    merged = _with_inlined_system_prompt("User prompt body", options)
    assert "System instructions:" in merged
    assert "User request:" in merged
    assert "Line1\n- item" in merged
    assert "Extra" in merged
    assert "User prompt body" in merged
