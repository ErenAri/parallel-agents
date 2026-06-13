from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from parallel_agents.agents.judge import run_judge
from parallel_agents.agents.planner import is_parse_failure, run_planner
from parallel_agents.agents.splitter import split_tasks
from parallel_agents.config import PipelineConfig
from parallel_agents.cost_tracker import PipelineCostTracker
from parallel_agents.evidence_store import BaseEvidenceStore, create_evidence_store
from parallel_agents.models import (
    FinalOutput,
    GitHubIssueContext,
    InputType,
    RunManifest,
    Subtask,
    TaskInput,
    TaskPlan,
    TaskStatus,
    WorkerResult,
)
from parallel_agents.patch_tools import validate_unified_diff
from parallel_agents.tools.github_tools import fetch_issue

logger = logging.getLogger("parallel_agents.pipeline")

WORKER_REGISTRY: dict[str, type] = {}


def _load_workers() -> None:
    if WORKER_REGISTRY:
        return
    from parallel_agents.agents.workers.security import SecurityWorker
    from parallel_agents.agents.workers.code import CodeWorker
    from parallel_agents.agents.workers.review import ReviewWorker
    from parallel_agents.agents.workers.test import TestWorker
    from parallel_agents.agents.workers.perf import PerfWorker
    from parallel_agents.agents.workers.devops import DevOpsWorker
    from parallel_agents.agents.workers.arch import ArchWorker
    from parallel_agents.agents.workers.docs import DocsWorker

    for cls in [SecurityWorker, CodeWorker, ReviewWorker, TestWorker, PerfWorker, DevOpsWorker, ArchWorker, DocsWorker]:
        WORKER_REGISTRY[cls.name] = cls


class Pipeline:
    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self.cost_tracker = PipelineCostTracker()
        _load_workers()

    def _detect_input_type(self, raw_input: str) -> InputType:
        if re.match(r"https?://github\.com/.+/issues/\d+", raw_input):
            return InputType.GITHUB_ISSUE
        if Path(raw_input).is_dir():
            return InputType.REPO_PATH
        return InputType.FREE_TEXT

    def _build_task_input(
        self, raw_input: str, repo_path: str | None = None
    ) -> TaskInput:
        input_type = self._detect_input_type(raw_input)

        github_url = raw_input if input_type == InputType.GITHUB_ISSUE else None
        if input_type == InputType.REPO_PATH and repo_path is None:
            repo_path = raw_input

        if repo_path:
            repo_path = str(Path(repo_path).resolve())

        return TaskInput(
            raw_input=raw_input,
            input_type=input_type,
            repo_path=repo_path,
            github_url=github_url,
        )

    async def run(
        self,
        raw_input: str,
        repo_path: str | None = None,
        on_status: Callable[[str], None] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        run_id: str | None = None,
    ) -> FinalOutput:
        task_input = self._build_task_input(raw_input, repo_path)
        run_id = run_id or uuid.uuid4().hex[:12]
        store = create_evidence_store(
            self.config.output_dir, run_id, self.config.store_backend
        )
        manifest = RunManifest(run_id=run_id, input=task_input)
        store.save_manifest(manifest)
        try:
            return await self._run_phases(
                task_input,
                run_id,
                store,
                manifest,
                on_status,
                on_event,
            )
        except Exception:
            # Persist FAILED so a crashed run is distinguishable from one
            # still in flight when reading the evidence store later.
            manifest.status = TaskStatus.FAILED
            try:
                store.save_manifest(manifest)
            except Exception:
                logger.exception("Could not persist FAILED status for run %s", run_id)
            raise

    async def _run_phases(
        self,
        task_input: TaskInput,
        run_id: str,
        store: BaseEvidenceStore,
        manifest: RunManifest,
        on_status: Callable[[str], None] | None,
        on_event: Callable[[dict[str, Any]], None] | None,
    ) -> FinalOutput:
        def _update_status(msg: str) -> None:
            logger.info(msg)
            if on_status:
                on_status(msg)

        def _trace(agent_name: str, entry: dict[str, Any]) -> None:
            store.append_trace(agent_name, entry)
            if on_event:
                on_event({"agent": agent_name, **entry})

        if task_input.github_url:
            _update_status("Resolving GitHub issue context...")
            issue = await fetch_issue(task_input.github_url)
            if not issue:
                error_summary = (
                    "Failed to fetch GitHub issue details. "
                    "Install and authenticate GitHub CLI (`gh auth login`), then try again."
                )
                manifest.status = TaskStatus.FAILED
                store.save_manifest(manifest)
                return FinalOutput(
                    summary=error_summary,
                    metadata={
                        "run_id": run_id,
                        "github_url": task_input.github_url,
                        "error": "github_issue_fetch_failed",
                    },
                )

            task_input.github_issue = GitHubIssueContext(
                number=issue.number,
                title=issue.title,
                body=issue.body,
                labels=issue.labels,
                state=issue.state,
                url=issue.url,
                comments=issue.comments,
            )
            manifest.input = task_input
            store.save_manifest(manifest)
            _update_status(f"Loaded issue #{issue.number}: {issue.title}")

        # Phase 1: Planning
        _update_status("Planning: analyzing repository and creating task plan...")
        manifest.phases["planning"] = {"status": "running", "started_at": _now_iso()}
        _trace("pipeline", {"phase": "planning", "status": "started", "ts": _now_iso()})
        planning_started = datetime.now(timezone.utc)
        plan = await run_planner(task_input, self.config)
        planning_completed = datetime.now(timezone.utc)
        store.save_plan(plan)
        manifest.phases["planning"]["status"] = "completed"
        manifest.phases["planning"]["completed_at"] = _now_iso()
        _trace("pipeline", {
            "phase": "planning", "status": "completed", "ts": _now_iso(),
            "subtask_count": len(plan.subtasks),
        })
        planner_metrics = plan.global_context.get("planner_metrics", {})
        self.cost_tracker.record_usage(
            agent_name="planner",
            model=self.config.planner_model,
            usage=planner_metrics.get("token_usage"),
            cost_usd=float(planner_metrics.get("total_cost_usd", 0.0) or 0.0),
            duration_ms=int((planning_completed - planning_started).total_seconds() * 1000),
        )

        if not plan.subtasks:
            if is_parse_failure(plan):
                _update_status("Planner output failed to parse after retries. Marking run failed.")
                manifest.status = TaskStatus.FAILED
                store.save_manifest(manifest)
                return FinalOutput(
                    summary="Planner failed to parse output after retries",
                    metadata={
                        "run_id": run_id,
                        "plan_summary": plan.summary,
                        "error": "planner_parse_failure",
                    },
                )
            _update_status("Planner produced no subtasks. Returning empty result.")
            manifest.status = TaskStatus.COMPLETED
            store.save_manifest(manifest)
            return FinalOutput(
                summary="No subtasks generated by planner",
                metadata={"run_id": run_id, "plan_summary": plan.summary},
            )

        # Phase 2: Splitting
        _update_status("Splitting tasks into parallel batches...")
        manifest.phases["splitting"] = {"status": "running", "started_at": _now_iso()}
        batches = split_tasks(plan, self.config)
        manifest.phases["splitting"]["status"] = "completed"
        manifest.phases["splitting"]["completed_at"] = _now_iso()
        _trace("pipeline", {
            "phase": "splitting", "status": "completed", "ts": _now_iso(),
            "batch_count": len(batches),
            "batches": [[s.assigned_worker for s in b] for b in batches],
        })

        # Phase 3: Worker Execution
        total_subtasks = sum(len(b) for b in batches)
        _update_status(f"Executing {total_subtasks} subtasks in {len(batches)} batch(es)...")
        manifest.phases["execution"] = {"status": "running", "started_at": _now_iso()}
        all_results: dict[str, WorkerResult] = {}

        semaphore = asyncio.Semaphore(self.config.max_parallel_workers)

        for batch_idx, batch in enumerate(batches):
            workers_in_batch = [s.assigned_worker for s in batch]
            _update_status(f"  Batch {batch_idx + 1}/{len(batches)}: {workers_in_batch}")
            _trace("pipeline", {
                "phase": "execution", "batch": batch_idx + 1,
                "workers": workers_in_batch, "status": "started", "ts": _now_iso(),
            })

            batch_results = await self._run_batch(batch, plan, semaphore, store, on_event)

            for result in batch_results:
                # Key by worker name for the common one-subtask-per-worker case,
                # but never silently overwrite a second subtask's result.
                result_key = result.worker_name
                if result_key in all_results:
                    result_key = f"{result.worker_name}:{result.subtask_id}"
                all_results[result_key] = result
                store.save_worker_result(result)

                # Track cost
                worker_config = self.config.workers.get(result.worker_name)
                model = worker_config.model if worker_config else "sonnet"
                self.cost_tracker.record_usage(
                    agent_name=result.worker_name,
                    model=model,
                    usage=result.token_usage,
                    cost_usd=result.cost_usd,
                    duration_ms=int(
                        (result.completed_at - result.started_at).total_seconds() * 1000
                    ),
                )

                _trace(result.worker_name, {
                    "status": result.status,
                    "findings": len(result.findings),
                    "recommendations": len(result.recommendations),
                    "ts": _now_iso(),
                })

            _trace("pipeline", {
                "phase": "execution", "batch": batch_idx + 1,
                "status": "completed", "ts": _now_iso(),
                "results": {r.worker_name: r.status for r in batch_results},
            })

        manifest.phases["execution"]["status"] = "completed"
        manifest.phases["execution"]["completed_at"] = _now_iso()
        manifest.workers_invoked = list(all_results.keys())

        # Phase 4: Judging
        _update_status("Judge is merging results and producing final output...")
        manifest.phases["judging"] = {"status": "running", "started_at": _now_iso()}
        _trace("pipeline", {"phase": "judging", "status": "started", "ts": _now_iso()})
        judging_started = datetime.now(timezone.utc)
        final_output = await run_judge(plan, all_results, self.config)
        _validate_and_normalize_patch(final_output)
        judging_completed = datetime.now(timezone.utc)
        manifest.phases["judging"]["status"] = "completed"
        manifest.phases["judging"]["completed_at"] = _now_iso()
        _trace("pipeline", {
            "phase": "judging", "status": "completed", "ts": _now_iso(),
            "risk_items": len(final_output.risk_report),
            "has_patch": final_output.patch is not None,
        })
        self.cost_tracker.record_usage(
            agent_name="judge",
            model=self.config.judge_model,
            usage=final_output.metadata.get("token_usage"),
            cost_usd=float(final_output.metadata.get("total_cost_usd", 0.0) or 0.0),
            duration_ms=int((judging_completed - judging_started).total_seconds() * 1000),
        )

        # Finalize cost tracking
        cost_summary = self.cost_tracker.summary()
        manifest.total_tokens = cost_summary["total_tokens"]
        manifest.total_cost_usd = cost_summary["total_cost_usd"]
        final_output.metadata["cost"] = cost_summary
        final_output.metadata["run_id"] = run_id
        store.save_final_output(final_output)

        manifest.status = TaskStatus.COMPLETED
        store.save_manifest(manifest)
        _update_status(
            f"Done. Run ID: {run_id} | "
            f"Tokens: {cost_summary['total_tokens']:,} | "
            f"Cost: ${cost_summary['total_cost_usd']:.4f}"
        )

        return final_output

    async def _run_batch(
        self,
        batch: list[Subtask],
        plan: TaskPlan,
        semaphore: asyncio.Semaphore,
        store: BaseEvidenceStore,
        on_event: Callable[[dict[str, Any]], None] | None,
    ) -> list[WorkerResult]:
        def _trace(agent_name: str, entry: dict[str, Any]) -> None:
            store.append_trace(agent_name, entry)
            if on_event:
                on_event({"agent": agent_name, **entry})

        async def _run_one(subtask: Subtask) -> WorkerResult:
            async with semaphore:
                worker_cls = WORKER_REGISTRY.get(subtask.assigned_worker)
                if not worker_cls:
                    return WorkerResult(
                        worker_name=subtask.assigned_worker,
                        subtask_id=subtask.id,
                        status="error",
                        raw_output=f"No worker registered for '{subtask.assigned_worker}'",
                    )

                worker_config = self.config.workers.get(subtask.assigned_worker)
                if not worker_config:
                    return WorkerResult(
                        worker_name=subtask.assigned_worker,
                        subtask_id=subtask.id,
                        status="error",
                        raw_output=f"No config for worker '{subtask.assigned_worker}'",
                    )

                worker = worker_cls(worker_config)
                _trace(worker.name, {
                    "event": "worker_started",
                    "subtask_id": subtask.id,
                    "ts": _now_iso(),
                })

                result = await worker.execute_with_retry(
                    subtask,
                    plan,
                    max_retries=self.config.max_retries,
                    retry_delay=self.config.retry_delay_seconds,
                    timeout=worker_config.timeout_seconds,
                )

                _trace(worker.name, {
                    "event": "worker_completed",
                    "subtask_id": subtask.id,
                    "status": result.status,
                    "ts": _now_iso(),
                })
                return result

        tasks = [_run_one(subtask) for subtask in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final: list[WorkerResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Unexpected error in worker %s: %s",
                    batch[i].assigned_worker, result,
                )
                final.append(WorkerResult(
                    worker_name=batch[i].assigned_worker,
                    subtask_id=batch[i].id,
                    status="error",
                    raw_output=f"Unexpected error: {result}",
                ))
            else:
                final.append(result)
        return final


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_and_normalize_patch(final_output: FinalOutput) -> None:
    """Validate judge patch before exposing it to CLI/MCP output."""
    if not final_output.patch:
        final_output.metadata["patch_validation"] = {
            "valid": False,
            "reason": "No patch generated.",
        }
        return

    valid, reason = validate_unified_diff(final_output.patch)
    final_output.metadata["patch_validation"] = {"valid": valid, "reason": reason}
    if not valid:
        final_output.metadata["invalid_patch"] = final_output.patch
        final_output.patch = None
        if "patch validation failed" not in final_output.summary.lower():
            final_output.summary = (
                f"{final_output.summary}\n\n"
                f"Note: patch validation failed and patch output was suppressed ({reason})."
            )
