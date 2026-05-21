from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ResultMessage,
    TextBlock,
    query,
)

from parallel_agents.config import WorkerConfig
from parallel_agents.claude_cli_fallback import run_query_via_cli
from parallel_agents.models import (
    Finding,
    Recommendation,
    Subtask,
    TaskPlan,
    WorkerResult,
)

logger = logging.getLogger("parallel_agents.worker")


class BaseWorker(ABC):
    name: str
    description: str

    def __init__(self, config: WorkerConfig) -> None:
        self.config = config

    @abstractmethod
    def system_prompt(self, subtask: Subtask, plan: TaskPlan) -> str: ...

    def build_user_prompt(self, subtask: Subtask, plan: TaskPlan) -> str:
        return (
            f"## Task\n{subtask.description}\n\n"
            f"## Repository Analysis\n{json.dumps(plan.repo_analysis, indent=2)}\n\n"
            f"## Context\n{json.dumps(subtask.context, indent=2)}\n\n"
            f"## Global Context\n{json.dumps(plan.global_context, indent=2)}\n\n"
            "Respond with a JSON object containing 'findings' and 'recommendations' arrays. "
            "Each finding has: severity, category, title, description, file_path, line_range, evidence. "
            "Each recommendation has: type, description, file_path, suggested_content, rationale, priority."
        )

    def get_options(self, subtask: Subtask, plan: TaskPlan) -> ClaudeCodeOptions:
        return ClaudeCodeOptions(
            system_prompt=self.system_prompt(subtask, plan),
            model=self.config.model,
            max_turns=self.config.max_turns,
            permission_mode=plan.global_context.get("permission_mode", "default"),
            cwd=plan.global_context.get("repo_path"),
        )

    async def execute(self, subtask: Subtask, plan: TaskPlan) -> WorkerResult:
        started_at = datetime.now(timezone.utc)
        options = self.get_options(subtask, plan)
        prompt = self.build_user_prompt(subtask, plan)

        parse_retry_attempts = _parse_retry_attempts_from_plan(plan)
        max_attempts = max(1, parse_retry_attempts + 1)
        parse_retries_used = 0
        raw_text = ""
        findings: list[Finding] = []
        recommendations: list[Recommendation] = []
        parsed_structured = False
        total_cost = 0.0
        token_usage: dict[str, int] = {}

        for attempt in range(max_attempts):
            attempt_prompt = (
                prompt if attempt == 0 else _build_parse_retry_prompt(prompt, raw_text)
            )
            raw_text, attempt_cost, attempt_usage = await _run_query_once(
                attempt_prompt, options
            )
            total_cost += attempt_cost
            _merge_token_usage(token_usage, attempt_usage)
            findings, recommendations, parsed_structured = _extract_structured_output_with_meta(
                raw_text
            )
            if parsed_structured:
                parse_retries_used = attempt
                break
            parse_retries_used = attempt + 1

        completed_at = datetime.now(timezone.utc)
        return self._parse_result(
            raw_text,
            subtask,
            started_at,
            completed_at,
            token_usage,
            total_cost,
            findings=findings,
            recommendations=recommendations,
            parsed_structured=parsed_structured,
            parse_retries_used=parse_retries_used,
        )

    async def execute_with_retry(
        self,
        subtask: Subtask,
        plan: TaskPlan,
        max_retries: int = 2,
        retry_delay: float = 5.0,
        timeout: float | None = None,
    ) -> WorkerResult:
        """Execute with exponential backoff retry and optional timeout."""
        timeout = timeout or self.config.timeout_seconds
        last_error: str = ""

        for attempt in range(max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self.execute(subtask, plan),
                    timeout=timeout,
                )
                if result.status != "error":
                    if attempt > 0:
                        logger.info(
                            "%s succeeded on attempt %d/%d",
                            self.name, attempt + 1, max_retries + 1,
                        )
                    return result
                last_error = result.raw_output
            except asyncio.TimeoutError:
                last_error = f"Timed out after {timeout}s"
                logger.warning(
                    "%s timed out on attempt %d/%d",
                    self.name, attempt + 1, max_retries + 1,
                )
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "%s failed on attempt %d/%d: %s",
                    self.name, attempt + 1, max_retries + 1, e,
                )

            if attempt < max_retries:
                delay = retry_delay * (2 ** attempt)
                logger.info("%s retrying in %.1fs...", self.name, delay)
                await asyncio.sleep(delay)

        return WorkerResult(
            worker_name=self.name,
            subtask_id=subtask.id,
            status="error",
            raw_output=f"Failed after {max_retries + 1} attempts. Last error: {last_error}",
        )

    def _parse_result(
        self,
        raw_output: str,
        subtask: Subtask,
        started_at: datetime,
        completed_at: datetime,
        token_usage: dict[str, Any],
        cost_usd: float,
        findings: list[Finding] | None = None,
        recommendations: list[Recommendation] | None = None,
        parsed_structured: bool | None = None,
        parse_retries_used: int = 0,
    ) -> WorkerResult:
        if findings is None or recommendations is None or parsed_structured is None:
            findings, recommendations, parsed_structured = _extract_structured_output_with_meta(
                raw_output
            )

        return WorkerResult(
            worker_name=self.name,
            subtask_id=subtask.id,
            status="success" if findings or recommendations else "partial",
            findings=findings,
            recommendations=recommendations,
            raw_output=raw_output,
            started_at=started_at,
            completed_at=completed_at,
            token_usage={
                **token_usage,
                "parse_retries_used": parse_retries_used,
                "parsed_structured_output": int(parsed_structured),
            }
            if token_usage or parse_retries_used or parsed_structured is not None
            else None,
            cost_usd=cost_usd,
        )


def _extract_structured_output(
    raw_output: str,
) -> tuple[list[Finding], list[Recommendation]]:
    findings, recommendations, _ = _extract_structured_output_with_meta(raw_output)
    return findings, recommendations


def _extract_structured_output_with_meta(
    raw_output: str,
) -> tuple[list[Finding], list[Recommendation], bool]:
    """Extract findings and recommendations from agent output.

    Tries multiple strategies for robustness:
    1. Find the outermost JSON object with findings/recommendations
    2. Try to find JSON in markdown code blocks
    3. Try to extract individual JSON arrays
    """
    findings: list[Finding] = []
    recommendations: list[Recommendation] = []

    # Strategy 1: code-fenced JSON block
    code_block = re.search(r"```(?:json)?\s*\n(\{[\s\S]*?\})\s*\n```", raw_output)
    if code_block:
        parsed = _try_parse_json(code_block.group(1))
        if parsed:
            findings, recommendations, has_schema = _extract_from_dict(parsed)
            if has_schema:
                return findings, recommendations, True

    # Strategy 2: outermost braces
    json_match = re.search(r"\{[\s\S]*\}", raw_output)
    if json_match:
        parsed = _try_parse_json(json_match.group())
        if parsed:
            findings, recommendations, has_schema = _extract_from_dict(parsed)
            if has_schema:
                return findings, recommendations, True

    # Strategy 3: find arrays directly
    has_schema = False
    for pattern, target in [
        (r'"findings"\s*:\s*(\[[\s\S]*?\])', "findings"),
        (r'"recommendations"\s*:\s*(\[[\s\S]*?\])', "recommendations"),
    ]:
        match = re.search(pattern, raw_output)
        if match:
            try:
                items = json.loads(match.group(1))
                if target == "findings":
                    findings = _parse_findings(items)
                else:
                    recommendations = _parse_recommendations(items)
                has_schema = True
            except json.JSONDecodeError:
                pass

    return findings, recommendations, has_schema


def _try_parse_json(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        # Try fixing common issues: trailing commas
        cleaned = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _extract_from_dict(
    data: dict[str, Any],
) -> tuple[list[Finding], list[Recommendation], bool]:
    has_schema = "findings" in data or "recommendations" in data
    findings = _parse_findings(data.get("findings", []))
    recommendations = _parse_recommendations(data.get("recommendations", []))
    return findings, recommendations, has_schema


def _parse_findings(items: list[Any]) -> list[Finding]:
    results: list[Finding] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            results.append(Finding(**item))
        except Exception:
            # Try with minimal required fields
            try:
                results.append(Finding(
                    severity=item.get("severity", "info"),
                    category=item.get("category", "unknown"),
                    title=item.get("title", "Untitled finding"),
                    description=item.get("description", str(item)),
                    file_path=item.get("file_path"),
                ))
            except Exception:
                pass
    return results


def _parse_recommendations(items: list[Any]) -> list[Recommendation]:
    results: list[Recommendation] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            results.append(Recommendation(**item))
        except Exception:
            try:
                results.append(Recommendation(
                    type=item.get("type", "code_change"),
                    description=item.get("description", str(item)),
                    file_path=item.get("file_path"),
                    suggested_content=item.get("suggested_content"),
                    rationale=item.get("rationale", ""),
                    priority=item.get("priority", "should"),
                ))
            except Exception:
                pass
    return results


async def _run_query_once(
    prompt: str,
    options: ClaudeCodeOptions,
) -> tuple[str, float, dict[str, int]]:
    raw_text = ""
    total_cost = 0.0
    token_usage: dict[str, int] = {}
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        raw_text += block.text
            elif isinstance(message, ResultMessage):
                total_cost = message.total_cost_usd or 0.0
                if message.usage:
                    token_usage = message.usage
        return raw_text, total_cost, token_usage
    except Exception as exc:
        logger.warning(
            "%s SDK query failed (%s). Falling back to direct Claude CLI.",
            __name__,
            exc,
        )
        fallback_text, fallback_cost, fallback_usage = await run_query_via_cli(prompt, options)
        if fallback_usage:
            fallback_usage["fallback_cli_used"] = 1
        else:
            fallback_usage = {"fallback_cli_used": 1}
        return fallback_text, fallback_cost, fallback_usage


def _merge_token_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    for key, value in usage.items():
        total[key] = total.get(key, 0) + value


def _parse_retry_attempts_from_plan(plan: TaskPlan) -> int:
    raw_value = plan.global_context.get("parse_retry_attempts", 1)
    try:
        return max(0, int(raw_value))
    except (TypeError, ValueError):
        return 1


def _build_parse_retry_prompt(base_prompt: str, previous_output: str) -> str:
    return (
        f"{base_prompt}\n\n"
        "Your previous response was not valid JSON for the required schema. "
        "Return ONLY valid JSON with keys 'findings' and 'recommendations'. "
        "Do not include markdown fences or extra text.\n\n"
        "Previous response:\n"
        f"{previous_output[:12000]}"
    )
