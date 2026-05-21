"""Thin facade between the desktop UI and the parallel_agents engine.

Keeps UI code free of direct imports of engine modules so we can swap
in-process calls for HTTP-to-gateway later without touching widgets.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from parallel_agents.company_artifacts import (
    append_company_artifact_event,
    persist_company_artifact,
)
from parallel_agents.company_workflows import (
    PlannedIssue,
    ProductBrief,
    RoadmapPlan,
    TechStackDecision,
    build_architecture_rfc,
    build_issue_plan_from_roadmap,
    build_prfaq,
    build_roadmap,
    build_sprint_plan,
    create_product_brief,
    recommend_tech_stack,
)
from parallel_agents.project_office import (
    init_project_office,
    list_office_run_ids,
    load_project_office,
    office_dir,
    office_output_dir,
    resolve_project_root,
)


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
        return self._load_project_info(root)

    def init_project(self, path: str | Path, name: str | None = None) -> ProjectInfo:
        root = resolve_project_root(path)
        init_project_office(root, name=name)
        self._current_project = root
        return self._load_project_info(root)

    def current_project(self) -> ProjectInfo | None:
        if self._current_project is None:
            return None
        return self._load_project_info(self._current_project)

    def require_project(self) -> Path:
        if self._current_project is None:
            raise RuntimeError("No project is open. Open a project first.")
        return self._current_project

    def _load_project_info(self, root: Path) -> ProjectInfo:
        payload = load_project_office(root)
        return ProjectInfo(
            name=payload.get("name", root.name),
            root=root,
            office_dir=office_dir(root),
            run_count=len(list_office_run_ids(root)),
            extra=payload,
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

    def latest_run_id(self) -> str | None:
        runs = list_office_run_ids(self._current_project) if self._current_project else []
        return runs[0] if runs else None

    def artifact_names_for_run(self, run_id: str) -> set[str]:
        return {p.stem for p in self.list_artifacts(run_id) if p.suffix == ".json" and p.stem != "index"}

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

    def _write_audit(self, run_id: str, event: dict[str, Any]) -> None:
        root = self.require_project()
        audit_dir = office_dir(root) / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": _iso_now(), "run_id": run_id, **event}
        with (audit_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record))
            fh.write("\n")


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
