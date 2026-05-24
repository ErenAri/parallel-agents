"""Thin facade between the desktop UI and the parallel_agents engine.

Keeps UI code free of direct imports of engine modules so we can swap
in-process calls for HTTP-to-gateway later without touching widgets.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from parallel_agents.company_artifacts import (
    append_company_artifact_event,
    persist_company_artifact,
)
from parallel_agents.company_workflows import (
    ProductBrief,
    RoadmapPlan,
    TechStackDecision,
    build_architecture_rfc,
    build_issue_plan_from_roadmap,
    build_prfaq,
    render_pr_summary,
    build_roadmap,
    build_sprint_plan,
    create_product_brief,
    recommend_tech_stack,
)
from parallel_agents.eval_harness import (
    EvaluationAggregate,
    EvaluationBreakdown,
    EvaluationBreakdownBucket,
    EvaluationGateResult,
    EvaluationResults,
    EvaluationScore,
    compute_evaluation_score,
    summarize_evaluation_results,
)
from parallel_agents.project_office import (
    init_project_office,
    list_office_run_ids,
    load_project_office,
    office_dir,
    office_output_dir,
    resolve_project_root,
    run_office_diagnostics,
    run_office_setup_fix,
)
from parallel_agents.pipeline import Pipeline
from parallel_agents.config import PipelineConfig


@dataclass
class ProjectInfo:
    name: str
    root: Path
    office_dir: Path
    run_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class BriefResult:
    run_id: str
    artifact_path: Path
    approval_path: Path


@dataclass
class ArtifactResult:
    run_id: str
    artifact: str
    artifact_path: Path
    approval_path: Path


@dataclass
class WorkspaceHome:
    project_name: str
    project_root: Path
    office_dir: Path
    run_count: int
    artifact_count: int
    pending_approval_count: int
    approved_approval_count: int
    rejected_approval_count: int
    latest_run_id: str | None
    current_branch: str | None
    recent_runs: list[dict[str, Any]]
    diagnostics_healthy: bool
    diagnostics_passed: int
    diagnostics_warnings: int
    diagnostics_failures: int
    diagnostics_checks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SetupFixResult:
    before: dict[str, Any]
    after: dict[str, Any]
    actions_taken: list[str] = field(default_factory=list)
    suggested_commands: list[str] = field(default_factory=list)


@dataclass
class ProductivitySnapshot:
    generated_at: str | None
    score_path: Path | None
    breakdown_path: Path | None
    gate_path: Path | None
    results_path: Path | None
    weighted_delivery_impact_score: float | None
    acceptance_rate: float | None
    regression_rate: float | None
    finding_precision: float | None
    case_count: int | None
    completed_count: int | None
    failed_count: int | None
    total_cost_usd: float | None
    total_duration_seconds: float | None
    gate_passed: bool | None
    gate_failed_rules: list[str]
    top_project: str | None
    top_workflow: str | None
    notes: list[str] = field(default_factory=list)


@dataclass
class ProductivityTrendPoint:
    generated_at: str
    score_path: Path
    weighted_delivery_impact_score: float | None
    acceptance_rate: float | None
    regression_rate: float | None
    finding_precision: float | None
    case_count: int
    completed_count: int
    failed_count: int
    gate_passed: bool | None
    total_cost_usd: float | None
    total_duration_seconds: float | None
    project_buckets: dict[str, "TrendBucketValue"] = field(default_factory=dict)
    workflow_buckets: dict[str, "TrendBucketValue"] = field(default_factory=dict)


@dataclass
class TrendBucketValue:
    case_count: int
    failed_count: int
    total_cost_usd: float
    total_duration_seconds: float


@dataclass
class ProductivityComparison:
    baseline_generated_at: str
    candidate_generated_at: str
    baseline_score_path: Path
    candidate_score_path: Path
    baseline_gate_path: Path | None
    candidate_gate_path: Path | None
    baseline_breakdown_path: Path | None
    candidate_breakdown_path: Path | None
    baseline_results_path: Path | None
    candidate_results_path: Path | None
    baseline_gate_passed: bool | None
    candidate_gate_passed: bool | None
    weighted_delivery_impact_delta: float | None
    acceptance_rate_delta: float | None
    regression_rate_delta: float | None
    finding_precision_delta: float | None
    completed_count_delta: int
    failed_count_delta: int
    case_count_delta: int
    total_cost_usd_delta: float | None
    total_duration_seconds_delta: float | None
    top_workflow_deltas: list["BucketDelta"] = field(default_factory=list)
    top_project_deltas: list["BucketDelta"] = field(default_factory=list)
    case_changes: list["CaseDelta"] = field(default_factory=list)


@dataclass
class BucketDelta:
    key: str
    case_count_delta: int
    failed_count_delta: int
    total_cost_usd_delta: float
    total_duration_seconds_delta: float


@dataclass
class CaseDelta:
    case_id: str
    baseline_run_id: str | None
    candidate_run_id: str | None
    baseline_status: str | None
    candidate_status: str | None
    duration_seconds_delta: float | None
    total_cost_usd_delta: float | None
    findings_count_delta: int | None
    recommendations_count_delta: int | None
    patch_generated_changed: bool


@dataclass
class PullRequestResult:
    run_id: str
    repo: str
    url: str
    title: str
    head: str
    base: str
    draft: bool
    summary_path: Path
    artifact_path: Path


@dataclass
class GitHubAuthStatus:
    installed: bool
    authenticated: bool
    status: str
    details: str
    login_command: str = "gh auth login -h github.com -w"


@dataclass
class PipelineRunResult:
    run_id: str
    summary: str
    output_path: Path
    total_tokens: int
    total_cost_usd: float
    worker_statuses: dict[str, str]


class EngineService:
    """In-process bridge to the engine. No async leaks into UI code."""

    def __init__(self) -> None:
        self._current_project: Path | None = None

    # -- project --------------------------------------------------------

    def open_project(self, path: str | Path) -> ProjectInfo:
        root = resolve_project_root(path)
        if not (office_dir(root) / "project.json").exists():
            init_project_office(root, name=root.name)
        self._current_project = root
        self._reload_settings()
        return self._load_project_info(root)

    def init_project(self, path: str | Path, name: str | None = None) -> ProjectInfo:
        root = resolve_project_root(path)
        init_project_office(root, name=name)
        self._current_project = root
        self._reload_settings()
        return self._load_project_info(root)

    def _reload_settings(self) -> None:
        from parallel_agents.desktop.services.settings_store import SettingsStore

        SettingsStore(self._current_project).load()

    def settings_store(self):
        from parallel_agents.desktop.services.settings_store import SettingsStore

        return SettingsStore(self._current_project)

    def current_project(self) -> ProjectInfo | None:
        if self._current_project is None:
            return None
        return self._load_project_info(self._current_project)

    def require_project(self) -> Path:
        if self._current_project is None:
            raise RuntimeError("No project is open. Open a project first.")
        return self._current_project

    def office_diagnostics(self) -> dict[str, Any]:
        root = self.require_project()
        return run_office_diagnostics(root)

    def fix_office_setup(self) -> SetupFixResult:
        root = self.require_project()
        payload = run_office_setup_fix(root)
        return SetupFixResult(
            before=dict(payload.get("before") or {}),
            after=dict(payload.get("after") or {}),
            actions_taken=list(payload.get("actions_taken") or []),
            suggested_commands=list(payload.get("suggested_commands") or []),
        )

    def _load_project_info(self, root: Path) -> ProjectInfo:
        payload = load_project_office(root)
        return ProjectInfo(
            name=payload.get("name", root.name),
            root=root,
            office_dir=office_dir(root),
            run_count=len(list_office_run_ids(root)),
            extra=payload,
        )

    # -- run execution -------------------------------------------------

    async def run_pipeline(
        self,
        task: str,
        *,
        on_status: Callable[[str], None] | None = None,
    ) -> PipelineRunResult:
        root = self.require_project()
        config = PipelineConfig(output_dir=str(office_output_dir(root)))
        pipeline = Pipeline(config)
        final_output = await pipeline.run(
            task,
            repo_path=str(root),
            on_status=on_status,
        )
        run_id = str(final_output.metadata.get("run_id", "")).strip()
        if not run_id:
            raise RuntimeError("Pipeline completed without a run_id.")

        output_path = persist_company_artifact(
            office_output_dir(root),
            run_id,
            "final-output",
            final_output.model_dump(mode="json"),
        )
        append_company_artifact_event(
            office_output_dir(root),
            run_id,
            "final-output",
            {"event": "created", "source": "desktop-runs", "task": task},
        )
        self._write_audit(
            run_id,
            {
                "event": "run.execute",
                "task": task,
                "repo": str(root),
                "has_patch": bool(final_output.patch),
            },
        )
        cost = final_output.metadata.get("cost", {})
        return PipelineRunResult(
            run_id=run_id,
            summary=final_output.summary,
            output_path=output_path,
            total_tokens=int(cost.get("total_tokens", 0) or 0),
            total_cost_usd=float(cost.get("total_cost_usd", 0.0) or 0.0),
            worker_statuses={
                name: str(result.status)
                for name, result in final_output.worker_results.items()
            },
        )

    # -- company workflows ---------------------------------------------

    def create_brief(self, idea: str, title: str | None = None) -> BriefResult:
        root = self.require_project()
        run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        brief = self._build_brief(idea, title=title)
        result = self._persist_artifact_with_approval(
            run_id=run_id,
            artifact="brief",
            payload=brief,
            title=brief.title,
            summary=brief.problem_statement,
            root=root,
        )
        return BriefResult(
            run_id=run_id,
            artifact_path=result.artifact_path,
            approval_path=result.approval_path,
        )

    def create_prfaq(self, run_id: str) -> ArtifactResult:
        root = self.require_project()
        brief = self._load_brief(run_id)
        prfaq = self._build_prfaq(brief)
        return self._persist_artifact_with_approval(
            run_id=run_id,
            artifact="prfaq",
            payload=prfaq,
            title=prfaq.headline,
            summary=prfaq.press_release_summary,
            root=root,
        )

    def create_roadmap(self, run_id: str, horizon_weeks: int = 12) -> ArtifactResult:
        root = self.require_project()
        brief = self._load_brief(run_id)
        roadmap = build_roadmap(brief, horizon_weeks=horizon_weeks)
        return self._persist_artifact_with_approval(
            run_id=run_id,
            artifact="roadmap",
            payload=roadmap,
            title=roadmap.name,
            summary=f"{len(roadmap.items)} items across {roadmap.horizon_weeks} weeks",
            root=root,
        )

    def create_tech_stack(self, run_id: str, repo_path: str | Path) -> ArtifactResult:
        root = self.require_project()
        stack = recommend_tech_stack(repo_path)
        return self._persist_artifact_with_approval(
            run_id=run_id,
            artifact="tech-stack",
            payload=stack,
            title=stack.recommended_option,
            summary=stack.rationale,
            root=root,
        )

    def create_rfc(self, run_id: str) -> ArtifactResult:
        root = self.require_project()
        brief = self._load_brief(run_id)
        stack = self._load_artifact(run_id, "tech-stack", TechStackDecision)
        rfc = self._build_rfc(brief, stack)
        return self._persist_artifact_with_approval(
            run_id=run_id,
            artifact="rfc",
            payload=rfc,
            title=rfc.title,
            summary=rfc.decision,
            root=root,
        )

    def create_sprint(self, run_id: str, milestone: str) -> ArtifactResult:
        root = self.require_project()
        roadmap = self._load_artifact(run_id, "roadmap", RoadmapPlan)
        sprint = build_sprint_plan(roadmap, milestone=milestone)
        return self._persist_artifact_with_approval(
            run_id=run_id,
            artifact="sprint",
            payload=sprint,
            title=sprint.name,
            summary=f"{len(sprint.items)} items, milestone {sprint.milestone}",
            root=root,
        )

    # -- github plan / apply (slice 2) ---------------------------------

    def create_issue_plan(self, run_id: str, repo: str) -> ArtifactResult:
        root = self.require_project()
        roadmap = self._load_artifact(run_id, "roadmap", RoadmapPlan)
        planned = build_issue_plan_from_roadmap(roadmap)
        payload = {
            "repo": repo,
            "issue_count": len(planned),
            "issues": [item.model_dump(mode="json") for item in planned],
            "requires_approval": True,
            "approved": False,
        }
        return self._persist_artifact_with_approval(
            run_id=run_id,
            artifact="issue-plan",
            payload=payload,
            title=f"Issue plan for {repo}",
            summary=f"{len(planned)} planned issues",
            root=root,
        )

    def apply_issue_plan(self, run_id: str, *, dry_run: bool = True) -> dict[str, Any]:
        """Apply an issue plan to GitHub. Live writes require `gh` to be authenticated."""
        import asyncio

        from parallel_agents.tools.github_apply import execute_company_issue_plan
        from parallel_agents.tools.github_tools import parse_repo_ref

        root = self.require_project()
        approval = self._find_approval(run_id, artifact="issue-plan")
        if approval is None:
            raise FileNotFoundError("No issue-plan approval found for this run.")
        if approval["data"].get("status") != "approved":
            raise PermissionError(
                "Issue plan must be approved before apply. "
                "Approve it on the Approvals page first."
            )

        plan_path = office_output_dir(root) / run_id / "company" / "issue-plan.json"
        if not plan_path.exists():
            raise FileNotFoundError(f"Issue-plan artifact missing: {plan_path}")
        plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))

        repo_ref = plan_payload.get("repo", "")
        parsed = parse_repo_ref(str(repo_ref))
        if not parsed:
            raise ValueError(f"Issue-plan repo ref is invalid: {repo_ref!r}")
        owner, repo = parsed

        issues = plan_payload.get("issues", [])
        result = asyncio.run(
            execute_company_issue_plan(
                owner=owner,
                repo=repo,
                issue_plan=issues,
                create_milestones=True,
                dry_run=dry_run,
            )
        )
        result["run_id"] = run_id
        result["mode"] = "dry-run" if dry_run else "live"
        result["applied_at"] = _iso_now()
        result["issues_planned"] = len(issues)
        milestone_names = sorted({i.get("milestone", "") for i in issues if i.get("milestone")})
        # narrow the top-level "milestones" if the executor returned it differently
        if not isinstance(result.get("milestones"), list):
            result["milestones"] = milestone_names
        persist_company_artifact(
            office_output_dir(root), run_id, "issue-plan-apply", result
        )
        self._write_audit(
            run_id,
            {
                "event": "issue-plan.apply",
                "mode": result["mode"],
                "issues_planned": result["issues_planned"],
            },
        )
        return result

    def create_pull_request(
        self,
        run_id: str,
        *,
        repo_ref: str,
        head: str,
        base: str = "main",
        title: str | None = None,
        draft: bool = True,
    ) -> PullRequestResult:
        import asyncio

        from parallel_agents.tools.github_tools import create_pr, parse_repo_ref

        root = self.require_project()
        parsed = parse_repo_ref(repo_ref)
        if not parsed:
            raise ValueError("repo must be owner/repo or a GitHub repository URL.")
        owner, repo = parsed

        clean_head = head.strip()
        clean_base = base.strip() or "main"
        if not clean_head:
            raise ValueError("head branch cannot be empty.")

        resolved_title = (title or "").strip() or f"Parallel Agents Office: {run_id}"
        summary_markdown = self._build_pr_summary(run_id)
        summary_path = office_output_dir(root) / run_id / "company" / "pr-summary.md"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(summary_markdown, encoding="utf-8")

        pr_url = asyncio.run(
            create_pr(
                owner,
                repo,
                resolved_title,
                summary_markdown,
                head=clean_head,
                base=clean_base,
                draft=draft,
            )
        )
        if not pr_url:
            raise RuntimeError(
                "Failed to create PR via gh. Verify `gh auth status`, repository access, and branch push."
            )

        payload = {
            "run_id": run_id,
            "repo": f"{owner}/{repo}",
            "url": pr_url,
            "title": resolved_title,
            "head": clean_head,
            "base": clean_base,
            "draft": draft,
            "summary_path": str(summary_path),
            "created_at": _iso_now(),
        }
        artifact_path = persist_company_artifact(
            office_output_dir(root),
            run_id,
            "pr-create",
            payload,
        )
        self._write_audit(
            run_id,
            {
                "event": "pr.create",
                "repo": payload["repo"],
                "url": payload["url"],
                "head": clean_head,
                "base": clean_base,
                "draft": draft,
            },
        )
        return PullRequestResult(
            run_id=run_id,
            repo=payload["repo"],
            url=pr_url,
            title=resolved_title,
            head=clean_head,
            base=clean_base,
            draft=draft,
            summary_path=summary_path,
            artifact_path=artifact_path,
        )

    def github_auth_status(self) -> GitHubAuthStatus:
        try:
            proc = subprocess.run(
                ["gh", "auth", "status", "--hostname", "github.com"],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return GitHubAuthStatus(
                installed=False,
                authenticated=False,
                status="missing",
                details="GitHub CLI (`gh`) is not installed or not on PATH.",
            )
        except Exception as exc:  # noqa: BLE001
            return GitHubAuthStatus(
                installed=True,
                authenticated=False,
                status="error",
                details=f"Failed to check gh auth status: {exc}",
            )

        details = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if stderr:
            details = f"{details}\n{stderr}".strip()
        if not details:
            details = "No output returned from `gh auth status`."

        if proc.returncode == 0:
            return GitHubAuthStatus(
                installed=True,
                authenticated=True,
                status="authenticated",
                details=details,
            )
        return GitHubAuthStatus(
            installed=True,
            authenticated=False,
            status="unauthenticated",
            details=details,
        )

    def workspace_home(self) -> WorkspaceHome:
        project = self.current_project()
        if project is None:
            raise RuntimeError("No project is open.")

        root = project.root
        runs = self.list_runs()
        approvals = self.list_all_approvals()

        artifact_count = 0
        recent_runs: list[dict[str, Any]] = []
        for run in runs:
            run_id = run["id"]
            artifacts = self.list_artifacts(run_id)
            artifact_count += len(artifacts)
            recent_runs.append(
                {
                    "id": run_id,
                    "created_at": run.get("created_at", ""),
                    "artifact_count": len(artifacts),
                }
            )

        statuses = [str(entry.get("data", {}).get("status", "pending")) for entry in approvals]
        diagnostics = run_office_diagnostics(root)
        return WorkspaceHome(
            project_name=project.name,
            project_root=root,
            office_dir=project.office_dir,
            run_count=len(runs),
            artifact_count=artifact_count,
            pending_approval_count=sum(1 for s in statuses if s == "pending"),
            approved_approval_count=sum(1 for s in statuses if s == "approved"),
            rejected_approval_count=sum(1 for s in statuses if s == "rejected"),
            latest_run_id=(runs[0]["id"] if runs else None),
            current_branch=self._git_current_branch(root),
            recent_runs=recent_runs[:8],
            diagnostics_healthy=bool(diagnostics.get("healthy", False)),
            diagnostics_passed=int(diagnostics.get("passed_checks", 0)),
            diagnostics_warnings=int(diagnostics.get("warning_checks", 0)),
            diagnostics_failures=int(diagnostics.get("failed_checks", 0)),
            diagnostics_checks=list(diagnostics.get("checks") or []),
        )

    def productivity_snapshot(self) -> ProductivitySnapshot:
        root = self.require_project()
        office_metrics_dir = office_dir(root) / "metrics"
        project_eval_dir = root / "eval"

        score_path = self._latest_existing_path(
            office_metrics_dir,
            ["*score*.json"],
        ) or self._latest_existing_path(project_eval_dir, ["*score*.json"])
        gate_path = self._latest_existing_path(
            office_metrics_dir,
            ["*gate*.json"],
        ) or self._latest_existing_path(project_eval_dir, ["*gate*.json"])
        breakdown_path = self._latest_existing_path(
            office_metrics_dir,
            ["*breakdown*.json"],
        ) or self._latest_existing_path(project_eval_dir, ["*breakdown*.json"])
        results_path = self._latest_existing_path(
            office_metrics_dir,
            ["*results*.json"],
        ) or self._latest_existing_path(project_eval_dir, ["*results*.json"])

        notes: list[str] = []

        score_obj = self._load_model(score_path, EvaluationScore)
        if score_path and score_obj is None:
            notes.append(f"Could not parse score file: {score_path.name}")

        gate_obj = self._load_model(gate_path, EvaluationGateResult)
        if gate_path and gate_obj is None:
            notes.append(f"Could not parse gate file: {gate_path.name}")

        aggregate: EvaluationAggregate | None = None
        if gate_obj is not None:
            aggregate = gate_obj.aggregate
            if score_obj is None:
                score_obj = gate_obj.score
                notes.append("Using score from gate artifact.")

        if score_obj is None and results_path is not None:
            results_obj = self._load_model(results_path, EvaluationResults)
            if results_obj is None:
                notes.append(f"Could not parse results file: {results_path.name}")
            else:
                score_obj = compute_evaluation_score(results_obj)
                aggregate = summarize_evaluation_results(results_obj)
                notes.append("Computed score from results artifact.")

        top_project: str | None = None
        top_workflow: str | None = None
        breakdown_obj = self._load_model(breakdown_path, EvaluationBreakdown)
        if breakdown_path and breakdown_obj is None:
            notes.append(f"Could not parse breakdown file: {breakdown_path.name}")
        if breakdown_obj is not None:
            if breakdown_obj.by_project:
                top_project = breakdown_obj.by_project[0].key
            if breakdown_obj.by_workflow:
                top_workflow = breakdown_obj.by_workflow[0].key

        if score_obj is None:
            notes.append("No evaluation score artifact found yet.")

        return ProductivitySnapshot(
            generated_at=(
                score_obj.generated_at.isoformat()
                if score_obj is not None
                else None
            ),
            score_path=score_path,
            breakdown_path=breakdown_path,
            gate_path=gate_path,
            results_path=results_path,
            weighted_delivery_impact_score=(
                score_obj.weighted_delivery_impact_score
                if score_obj is not None
                else None
            ),
            acceptance_rate=score_obj.acceptance_rate if score_obj is not None else None,
            regression_rate=score_obj.regression_rate if score_obj is not None else None,
            finding_precision=score_obj.finding_precision if score_obj is not None else None,
            case_count=score_obj.case_count if score_obj is not None else None,
            completed_count=score_obj.completed_count if score_obj is not None else None,
            failed_count=score_obj.failed_count if score_obj is not None else None,
            total_cost_usd=aggregate.total_cost_usd if aggregate is not None else None,
            total_duration_seconds=(
                aggregate.total_duration_seconds if aggregate is not None else None
            ),
            gate_passed=gate_obj.passed if gate_obj is not None else None,
            gate_failed_rules=(gate_obj.failed_rules if gate_obj is not None else []),
            top_project=top_project,
            top_workflow=top_workflow,
            notes=notes,
        )

    def productivity_trend(self, *, limit: int = 8) -> list[ProductivityTrendPoint]:
        root = self.require_project()
        office_metrics_dir = office_dir(root) / "metrics"
        project_eval_dir = root / "eval"

        score_files = self._list_matching_paths(
            [office_metrics_dir, project_eval_dir],
            ["*score*.json"],
        )

        points: list[ProductivityTrendPoint] = []
        for path in score_files:
            score = self._load_model(path, EvaluationScore)
            if score is None:
                continue

            gate = self._load_related_gate(path)
            aggregate = gate.aggregate if gate is not None else None
            breakdown = self._load_related_breakdown(path)
            points.append(
                ProductivityTrendPoint(
                    generated_at=score.generated_at.isoformat(),
                    score_path=path,
                    weighted_delivery_impact_score=score.weighted_delivery_impact_score,
                    acceptance_rate=score.acceptance_rate,
                    regression_rate=score.regression_rate,
                    finding_precision=score.finding_precision,
                    case_count=score.case_count,
                    completed_count=score.completed_count,
                    failed_count=score.failed_count,
                    gate_passed=(gate.passed if gate is not None else None),
                    total_cost_usd=(aggregate.total_cost_usd if aggregate is not None else None),
                    total_duration_seconds=(
                        aggregate.total_duration_seconds if aggregate is not None else None
                    ),
                    project_buckets=self._bucket_map(
                        breakdown.by_project if breakdown is not None else []
                    ),
                    workflow_buckets=self._bucket_map(
                        breakdown.by_workflow if breakdown is not None else []
                    ),
                )
            )

        points.sort(key=lambda item: item.generated_at, reverse=True)
        if limit <= 0:
            return []
        return points[:limit]

    def compare_productivity_snapshots(
        self,
        *,
        baseline_score_path: str | Path,
        candidate_score_path: str | Path,
    ) -> ProductivityComparison:
        baseline_path = Path(baseline_score_path).resolve()
        candidate_path = Path(candidate_score_path).resolve()

        baseline_score = self._load_model(baseline_path, EvaluationScore)
        if baseline_score is None:
            raise FileNotFoundError(f"Could not load baseline score: {baseline_path}")
        candidate_score = self._load_model(candidate_path, EvaluationScore)
        if candidate_score is None:
            raise FileNotFoundError(f"Could not load candidate score: {candidate_path}")

        baseline_gate_path, baseline_gate = self._resolve_related_gate(baseline_path)
        candidate_gate_path, candidate_gate = self._resolve_related_gate(candidate_path)
        baseline_breakdown_path, baseline_breakdown = self._resolve_related_breakdown(
            baseline_path
        )
        candidate_breakdown_path, candidate_breakdown = self._resolve_related_breakdown(
            candidate_path
        )
        baseline_results_path, baseline_results = self._resolve_related_results(
            baseline_path
        )
        candidate_results_path, candidate_results = self._resolve_related_results(
            candidate_path
        )

        baseline_cost = (
            baseline_gate.aggregate.total_cost_usd if baseline_gate is not None else None
        )
        candidate_cost = (
            candidate_gate.aggregate.total_cost_usd if candidate_gate is not None else None
        )
        baseline_duration = (
            baseline_gate.aggregate.total_duration_seconds
            if baseline_gate is not None
            else None
        )
        candidate_duration = (
            candidate_gate.aggregate.total_duration_seconds
            if candidate_gate is not None
            else None
        )
        workflow_deltas = self._compute_bucket_deltas(
            baseline_breakdown.by_workflow if baseline_breakdown is not None else [],
            candidate_breakdown.by_workflow if candidate_breakdown is not None else [],
        )
        project_deltas = self._compute_bucket_deltas(
            baseline_breakdown.by_project if baseline_breakdown is not None else [],
            candidate_breakdown.by_project if candidate_breakdown is not None else [],
        )
        case_changes = self._compute_case_deltas(
            baseline_results,
            candidate_results,
        )

        return ProductivityComparison(
            baseline_generated_at=baseline_score.generated_at.isoformat(),
            candidate_generated_at=candidate_score.generated_at.isoformat(),
            baseline_score_path=baseline_path,
            candidate_score_path=candidate_path,
            baseline_gate_path=baseline_gate_path,
            candidate_gate_path=candidate_gate_path,
            baseline_breakdown_path=baseline_breakdown_path,
            candidate_breakdown_path=candidate_breakdown_path,
            baseline_results_path=baseline_results_path,
            candidate_results_path=candidate_results_path,
            baseline_gate_passed=(
                baseline_gate.passed if baseline_gate is not None else None
            ),
            candidate_gate_passed=(
                candidate_gate.passed if candidate_gate is not None else None
            ),
            weighted_delivery_impact_delta=_metric_delta(
                candidate_score.weighted_delivery_impact_score,
                baseline_score.weighted_delivery_impact_score,
            ),
            acceptance_rate_delta=_metric_delta(
                candidate_score.acceptance_rate,
                baseline_score.acceptance_rate,
            ),
            regression_rate_delta=_metric_delta(
                candidate_score.regression_rate,
                baseline_score.regression_rate,
            ),
            finding_precision_delta=_metric_delta(
                candidate_score.finding_precision,
                baseline_score.finding_precision,
            ),
            completed_count_delta=(
                candidate_score.completed_count - baseline_score.completed_count
            ),
            failed_count_delta=(candidate_score.failed_count - baseline_score.failed_count),
            case_count_delta=(candidate_score.case_count - baseline_score.case_count),
            total_cost_usd_delta=_metric_delta(candidate_cost, baseline_cost),
            total_duration_seconds_delta=_metric_delta(
                candidate_duration, baseline_duration
            ),
            top_workflow_deltas=workflow_deltas[:6],
            top_project_deltas=project_deltas[:6],
            case_changes=case_changes[:12],
        )

    def latest_run_id(self) -> str | None:
        runs = list_office_run_ids(self._current_project) if self._current_project else []
        return runs[0] if runs else None

    def artifact_names_for_run(self, run_id: str) -> set[str]:
        return {p.stem for p in self.list_artifacts(run_id) if p.suffix == ".json" and p.stem != "index"}

    def roadmap_milestones(self, run_id: str | None) -> list[str]:
        """Ordered unique milestones from a run's roadmap artifact, or []."""
        if run_id is None:
            return []
        try:
            roadmap = self._load_artifact(run_id, "roadmap", RoadmapPlan)
        except FileNotFoundError:
            return []
        seen: list[str] = []
        for item in roadmap.items:
            ms = (item.milestone or "").strip()
            if ms and ms not in seen:
                seen.append(ms)
        return seen

    def _load_brief(self, run_id: str) -> ProductBrief:
        return self._load_artifact(run_id, "brief", ProductBrief)

    def _load_artifact(self, run_id: str, name: str, model_cls):
        root = self.require_project()
        path = office_output_dir(root) / run_id / "company" / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Artifact '{name}' not found for run {run_id}. Generate it first."
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return model_cls.model_validate(data)

    def _load_artifact_payload(self, run_id: str, name: str) -> dict[str, Any] | None:
        root = self.require_project()
        path = office_output_dir(root) / run_id / "company" / f"{name}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _build_pr_summary(self, run_id: str) -> str:
        root = self.require_project()
        final_output = self._load_artifact_payload(run_id, "final-output")
        if final_output is None:
            apply_payload = self._load_artifact_payload(run_id, "issue-plan-apply")
            if apply_payload is not None:
                created = sum(
                    1 for issue in apply_payload.get("issues", [])
                    if isinstance(issue, dict) and issue.get("created")
                )
                planned = int(apply_payload.get("issues_planned", 0) or 0)
                mode = str(apply_payload.get("mode", "unknown"))
                repo = str(apply_payload.get("repo", "unknown"))
                final_output = {
                    "summary": (
                        f"Company run `{run_id}` generated GitHub plan/apply output "
                        f"for `{repo}` ({mode}, {created}/{planned} issues created)."
                    ),
                    "risk_report": [],
                    "metadata": {"tests_run": []},
                }
            else:
                brief_payload = self._load_artifact_payload(run_id, "brief") or {}
                brief_title = str(brief_payload.get("title", "")).strip() or f"Run {run_id}"
                final_output = {
                    "summary": f"Parallel Agents Office artifacts for `{brief_title}`.",
                    "risk_report": [],
                    "metadata": {"tests_run": []},
                }
        artifacts = {
            path.stem: str(path.relative_to(office_dir(root)))
            for path in self.list_artifacts(run_id)
        }
        return render_pr_summary(final_output, run_id=run_id, artifacts=artifacts)

    def _find_approval(self, run_id: str, *, artifact: str) -> dict[str, Any] | None:
        for entry in self._list_approvals(status=None):
            data = entry["data"]
            if data.get("run_id") == run_id and data.get("artifact") == artifact:
                return entry
        return None

    # -- LLM-backed generation (with deterministic fallback) -----------

    def _build_brief(self, idea: str, *, title: str | None) -> ProductBrief:
        import os

        if not _truthy(os.environ.get("PA_DESKTOP_LLM_BRIEF")):
            return create_product_brief(idea, title=title)
        try:
            from parallel_agents.desktop.services.llm_brief import generate_llm_brief

            return generate_llm_brief(idea, title=title)
        except Exception:
            return create_product_brief(idea, title=title)

    def _build_prfaq(self, brief: ProductBrief):
        import os

        if not _truthy(os.environ.get("PA_DESKTOP_LLM_PRFAQ")):
            return build_prfaq(brief)
        try:
            from parallel_agents.desktop.services.llm_prfaq import generate_llm_prfaq

            return generate_llm_prfaq(brief)
        except Exception:
            return build_prfaq(brief)

    def _build_rfc(self, brief: ProductBrief, stack: TechStackDecision):
        import os

        if not _truthy(os.environ.get("PA_DESKTOP_LLM_RFC")):
            return build_architecture_rfc(brief, stack)
        try:
            from parallel_agents.desktop.services.llm_rfc import generate_llm_rfc

            return generate_llm_rfc(brief, stack)
        except Exception:
            return build_architecture_rfc(brief, stack)

    def _persist_artifact_with_approval(
        self,
        *,
        run_id: str,
        artifact: str,
        payload,
        title: str,
        summary: str,
        root: Path,
    ) -> ArtifactResult:
        output_dir = office_output_dir(root)
        artifact_path = persist_company_artifact(output_dir, run_id, artifact, payload)
        append_company_artifact_event(
            output_dir,
            run_id,
            artifact,
            {"event": "created", "source": "desktop", "title": title},
        )
        approval_path = self._create_pending_approval(
            run_id=run_id,
            artifact=artifact,
            title=title,
            summary=summary,
            artifact_relpath=str(artifact_path.relative_to(office_dir(root))),
        )
        return ArtifactResult(
            run_id=run_id,
            artifact=artifact,
            artifact_path=artifact_path,
            approval_path=approval_path,
        )

    # -- runs / artifacts ----------------------------------------------

    def list_runs(self) -> list[dict[str, Any]]:
        root = self._current_project
        if root is None:
            return []
        runs: list[dict[str, Any]] = []
        for run_id in list_office_run_ids(root):
            run_dir = office_dir(root) / run_id
            runs.append(
                {
                    "id": run_id,
                    "path": run_dir,
                    "created_at": _stat_iso(run_dir),
                }
            )
        return runs

    def list_artifacts(self, run_id: str) -> list[Path]:
        root = self._current_project
        if root is None:
            return []
        company_dir = office_dir(root) / run_id / "company"
        if not company_dir.exists():
            return []
        return sorted(p for p in company_dir.iterdir() if p.is_file())

    # -- approvals ------------------------------------------------------

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        return self._list_approvals(status="pending")

    def list_all_approvals(self) -> list[dict[str, Any]]:
        return self._list_approvals(status=None)

    def approve(self, approval_path: Path, approver: str, note: str = "") -> dict[str, Any]:
        return self._decide_approval(
            approval_path, decision="approved", actor=approver, message=note
        )

    def reject(self, approval_path: Path, approver: str, reason: str = "") -> dict[str, Any]:
        return self._decide_approval(
            approval_path, decision="rejected", actor=approver, message=reason
        )

    def _create_pending_approval(
        self,
        *,
        run_id: str,
        artifact: str,
        title: str,
        summary: str,
        artifact_relpath: str,
    ) -> Path:
        root = self.require_project()
        approvals_dir = office_dir(root) / "approvals"
        approvals_dir.mkdir(parents=True, exist_ok=True)
        approval_id = f"{run_id}-{artifact}"
        path = approvals_dir / f"{approval_id}.json"
        payload = {
            "approval_id": approval_id,
            "run_id": run_id,
            "artifact": artifact,
            "artifact_path": artifact_relpath,
            "title": title,
            "summary": summary,
            "status": "pending",
            "created_at": _iso_now(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._write_audit(
            run_id,
            {"event": "approval.created", "approval_id": approval_id, "artifact": artifact},
        )
        return path

    def _decide_approval(
        self, approval_path: Path, *, decision: str, actor: str, message: str
    ) -> dict[str, Any]:
        if not approval_path.exists():
            raise FileNotFoundError(f"Approval not found: {approval_path}")
        data = json.loads(approval_path.read_text(encoding="utf-8"))
        if data.get("status") != "pending":
            raise ValueError(
                f"Approval is already {data.get('status')!r}; cannot {decision}."
            )
        data["status"] = decision
        data["decided_by"] = actor
        data["decided_at"] = _iso_now()
        if decision == "approved":
            data["approval_note"] = message
        else:
            data["rejection_reason"] = message
        approval_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._write_audit(
            data.get("run_id", "unknown"),
            {
                "event": f"approval.{decision}",
                "approval_id": data.get("approval_id"),
                "artifact": data.get("artifact"),
                "actor": actor,
                "message": message,
            },
        )
        return data

    def _list_approvals(self, *, status: str | None) -> list[dict[str, Any]]:
        root = self._current_project
        if root is None:
            return []
        approvals_dir = office_dir(root) / "approvals"
        if not approvals_dir.exists():
            return []
        entries: list[dict[str, Any]] = []
        for path in sorted(approvals_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if status is None or data.get("status", "pending") == status:
                entries.append({"path": path, "data": data})
        return entries

    def list_audit_events(
        self,
        *,
        run_id: str | None = None,
        approval_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        root = self._current_project
        if root is None:
            return []
        audit_path = office_dir(root) / "audit" / "events.jsonl"
        if not audit_path.exists():
            return []

        events: list[dict[str, Any]] = []
        for line in audit_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if run_id and str(payload.get("run_id", "")) != run_id:
                continue
            if approval_id and str(payload.get("approval_id", "")) != approval_id:
                continue
            events.append(payload)
        if limit > 0:
            return events[-limit:]
        return events

    def _write_audit(self, run_id: str, event: dict[str, Any]) -> None:
        root = self.require_project()
        audit_dir = office_dir(root) / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": _iso_now(), "run_id": run_id, **event}
        with (audit_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record))
            fh.write("\n")

    @staticmethod
    def _git_current_branch(root: Path) -> str | None:
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(root),
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception:
            return None
        if proc.returncode != 0:
            return None
        branch = proc.stdout.strip()
        return branch or None

    @staticmethod
    def _latest_existing_path(base_dir: Path, patterns: list[str]) -> Path | None:
        if not base_dir.exists():
            return None
        candidates: list[Path] = []
        for pattern in patterns:
            for path in base_dir.glob(pattern):
                if path.is_file():
                    candidates.append(path)
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    @staticmethod
    def _load_model(path: Path | None, model_cls):
        if path is None or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        try:
            return model_cls.model_validate(payload)
        except Exception:
            return None

    @staticmethod
    def _list_matching_paths(base_dirs: list[Path], patterns: list[str]) -> list[Path]:
        found: dict[str, Path] = {}
        for base_dir in base_dirs:
            if not base_dir.exists():
                continue
            for pattern in patterns:
                for path in base_dir.glob(pattern):
                    if path.is_file():
                        found[str(path.resolve())] = path
        return sorted(found.values(), key=lambda p: p.stat().st_mtime, reverse=True)

    def _load_related_gate(self, score_path: Path) -> EvaluationGateResult | None:
        _path, gate = self._resolve_related_gate(score_path)
        return gate

    def _resolve_related_gate(
        self,
        score_path: Path,
    ) -> tuple[Path | None, EvaluationGateResult | None]:
        candidates = [
            score_path.with_name(score_path.name.replace("score", "gate")),
            score_path.with_name(score_path.name.replace("Score", "Gate")),
            score_path.parent / "eval-gate.json",
            score_path.parent / "gate.json",
        ]
        for candidate in candidates:
            gate = self._load_model(candidate, EvaluationGateResult)
            if gate is not None:
                return candidate.resolve(), gate
        return None, None

    def _load_related_breakdown(self, score_path: Path) -> EvaluationBreakdown | None:
        _path, breakdown = self._resolve_related_breakdown(score_path)
        return breakdown

    def _resolve_related_breakdown(
        self,
        score_path: Path,
    ) -> tuple[Path | None, EvaluationBreakdown | None]:
        candidates = [
            score_path.with_name(score_path.name.replace("score", "breakdown")),
            score_path.with_name(score_path.name.replace("Score", "Breakdown")),
            score_path.parent / "eval-breakdown.json",
            score_path.parent / "breakdown.json",
        ]
        for candidate in candidates:
            breakdown = self._load_model(candidate, EvaluationBreakdown)
            if breakdown is not None:
                return candidate.resolve(), breakdown
        return None, None

    def _load_related_results(self, score_path: Path) -> EvaluationResults | None:
        _path, results = self._resolve_related_results(score_path)
        return results

    def _resolve_related_results(
        self,
        score_path: Path,
    ) -> tuple[Path | None, EvaluationResults | None]:
        candidates = [
            score_path.with_name(score_path.name.replace("score", "results")),
            score_path.with_name(score_path.name.replace("Score", "Results")),
            score_path.parent / "eval-results.json",
            score_path.parent / "results.json",
        ]
        for candidate in candidates:
            results = self._load_model(candidate, EvaluationResults)
            if results is not None:
                return candidate.resolve(), results
        return None, None

    @staticmethod
    def _bucket_map(
        buckets: list[EvaluationBreakdownBucket],
    ) -> dict[str, TrendBucketValue]:
        mapped: dict[str, TrendBucketValue] = {}
        for bucket in buckets:
            mapped[bucket.key] = TrendBucketValue(
                case_count=bucket.case_count,
                failed_count=bucket.failed_count,
                total_cost_usd=bucket.total_cost_usd,
                total_duration_seconds=bucket.total_duration_seconds,
            )
        return mapped

    @staticmethod
    def _compute_bucket_deltas(
        baseline: list[EvaluationBreakdownBucket],
        candidate: list[EvaluationBreakdownBucket],
    ) -> list[BucketDelta]:
        baseline_map = {entry.key: entry for entry in baseline}
        candidate_map = {entry.key: entry for entry in candidate}
        keys = sorted(set(baseline_map) | set(candidate_map))
        deltas: list[BucketDelta] = []
        for key in keys:
            b = baseline_map.get(key)
            c = candidate_map.get(key)
            b_case = b.case_count if b is not None else 0
            c_case = c.case_count if c is not None else 0
            b_failed = b.failed_count if b is not None else 0
            c_failed = c.failed_count if c is not None else 0
            b_cost = b.total_cost_usd if b is not None else 0.0
            c_cost = c.total_cost_usd if c is not None else 0.0
            b_duration = b.total_duration_seconds if b is not None else 0.0
            c_duration = c.total_duration_seconds if c is not None else 0.0
            delta = BucketDelta(
                key=key,
                case_count_delta=(c_case - b_case),
                failed_count_delta=(c_failed - b_failed),
                total_cost_usd_delta=(c_cost - b_cost),
                total_duration_seconds_delta=(c_duration - b_duration),
            )
            deltas.append(delta)
        deltas.sort(
            key=lambda entry: (
                abs(entry.total_cost_usd_delta)
                + abs(entry.total_duration_seconds_delta) / 60.0
                + abs(entry.failed_count_delta) * 2
                + abs(entry.case_count_delta)
            ),
            reverse=True,
        )
        return deltas

    @staticmethod
    def _compute_case_deltas(
        baseline: EvaluationResults | None,
        candidate: EvaluationResults | None,
    ) -> list[CaseDelta]:
        if baseline is None or candidate is None:
            return []
        baseline_map = {entry.case_id: entry for entry in baseline.runs}
        candidate_map = {entry.case_id: entry for entry in candidate.runs}
        keys = sorted(set(baseline_map) | set(candidate_map))
        changes: list[CaseDelta] = []
        for case_id in keys:
            b = baseline_map.get(case_id)
            c = candidate_map.get(case_id)
            baseline_status = b.status if b is not None else None
            candidate_status = c.status if c is not None else None
            duration_delta = None
            if b is not None and c is not None:
                duration_delta = c.duration_seconds - b.duration_seconds
            cost_delta = None
            if b is not None and c is not None:
                cost_delta = c.total_cost_usd - b.total_cost_usd
            findings_delta = None
            if b is not None and c is not None:
                findings_delta = c.findings_count - b.findings_count
            recs_delta = None
            if b is not None and c is not None:
                recs_delta = c.recommendations_count - b.recommendations_count
            patch_changed = (
                b is not None and c is not None and b.patch_generated != c.patch_generated
            )

            status_changed = baseline_status != candidate_status
            if not status_changed and duration_delta is None and cost_delta is None and not patch_changed:
                continue
            if (
                not status_changed
                and abs(duration_delta or 0.0) < 0.001
                and abs(cost_delta or 0.0) < 0.000001
                and not patch_changed
                and (findings_delta or 0) == 0
                and (recs_delta or 0) == 0
            ):
                continue

            changes.append(
                CaseDelta(
                    case_id=case_id,
                    baseline_run_id=(b.run_id if b is not None else None),
                    candidate_run_id=(c.run_id if c is not None else None),
                    baseline_status=baseline_status,
                    candidate_status=candidate_status,
                    duration_seconds_delta=duration_delta,
                    total_cost_usd_delta=cost_delta,
                    findings_count_delta=findings_delta,
                    recommendations_count_delta=recs_delta,
                    patch_generated_changed=patch_changed,
                )
            )

        changes.sort(
            key=lambda entry: (
                1 if entry.baseline_status != entry.candidate_status else 0,
                abs(entry.total_cost_usd_delta or 0.0)
                + abs(entry.duration_seconds_delta or 0.0) / 60.0
                + abs(entry.findings_count_delta or 0)
                + abs(entry.recommendations_count_delta or 0),
            ),
            reverse=True,
        )
        return changes


def _stat_iso(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _truthy(value: str | None) -> bool:
    return bool(value) and value.strip().lower() in {"1", "true", "yes", "on"}


def _metric_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline
