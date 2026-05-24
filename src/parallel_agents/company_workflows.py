from __future__ import annotations

from collections.abc import Mapping
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "project"


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _derive_title(idea: str) -> str:
    words = idea.split()
    if not words:
        return "Untitled Project"
    return " ".join(words[:8]).strip().title()


class FAQItem(BaseModel):
    question: str
    answer: str


class ProductBrief(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=_utc_now)
    title: str
    idea: str
    problem_statement: str
    target_users: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class PRFAQDocument(BaseModel):
    created_at: datetime = Field(default_factory=_utc_now)
    headline: str
    press_release_summary: str
    customer_faq: list[FAQItem] = Field(default_factory=list)
    internal_faq: list[FAQItem] = Field(default_factory=list)
    launch_criteria: list[str] = Field(default_factory=list)


class TechOptionScore(BaseModel):
    option_name: str
    scores: dict[str, int]
    total_score: int
    notes: str


class TechStackDecision(BaseModel):
    created_at: datetime = Field(default_factory=_utc_now)
    context: str
    constraints: list[str] = Field(default_factory=list)
    options: list[TechOptionScore] = Field(default_factory=list)
    recommended_option: str
    rationale: str
    risks: list[str] = Field(default_factory=list)
    detected_signals: list[str] = Field(default_factory=list)


class ArchitectureRFC(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=_utc_now)
    title: str
    status: Literal["proposed", "accepted", "rejected"] = "proposed"
    context: str
    decision: str
    alternatives: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    security_considerations: list[str] = Field(default_factory=list)
    rollout_plan: list[str] = Field(default_factory=list)


class RoadmapItem(BaseModel):
    id: str
    title: str
    owner_role: str
    milestone: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class RoadmapPlan(BaseModel):
    created_at: datetime = Field(default_factory=_utc_now)
    name: str
    horizon_weeks: int
    outcomes: list[str] = Field(default_factory=list)
    items: list[RoadmapItem] = Field(default_factory=list)


class SprintPlanItem(BaseModel):
    source_item_id: str
    title: str
    owner_role: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    status: Literal["planned", "in_progress", "blocked", "done"] = "planned"


class SprintPlan(BaseModel):
    created_at: datetime = Field(default_factory=_utc_now)
    name: str
    milestone: str
    horizon_days: int
    goals: list[str] = Field(default_factory=list)
    items: list[SprintPlanItem] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class PlannedIssue(BaseModel):
    source_item_id: str
    title: str
    body: str
    milestone: str
    labels: list[str] = Field(default_factory=list)


class ReleaseCheckItem(BaseModel):
    name: str
    status: Literal["pass", "warn", "fail"]
    details: str


class ReleaseReadinessReport(BaseModel):
    created_at: datetime = Field(default_factory=_utc_now)
    repo_path: str
    status: Literal["ready", "needs_attention", "blocked"]
    items: list[ReleaseCheckItem] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class PostReleaseFollowUp(BaseModel):
    title: str
    owner_role: str
    priority: Literal["low", "medium", "high"] = "medium"
    source: str
    status: Literal["open", "in_progress", "done"] = "open"


class PostReleaseReview(BaseModel):
    created_at: datetime = Field(default_factory=_utc_now)
    release_id: str
    summary: str
    outcomes: list[str] = Field(default_factory=list)
    incidents: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    follow_up_items: list[PostReleaseFollowUp] = Field(default_factory=list)


def create_product_brief(idea: str, title: str | None = None) -> ProductBrief:
    normalized_idea = _normalize_text(idea)
    if not normalized_idea:
        raise ValueError("Idea cannot be empty.")

    resolved_title = _normalize_text(title) if title else _derive_title(normalized_idea)
    if not resolved_title:
        resolved_title = _derive_title(normalized_idea)

    return ProductBrief(
        id=f"brief-{_slugify(resolved_title)}",
        title=resolved_title,
        idea=normalized_idea,
        problem_statement=normalized_idea,
        target_users=[
            "Solo builders",
            "Small software teams",
            "Engineering leads",
        ],
        goals=[
            "Turn project ideas into a delivery-ready plan",
            "Produce measurable quality and productivity gains",
            "Generate reviewable implementation artifacts",
        ],
        non_goals=[
            "Fully autonomous production deployment by default",
            "General-purpose personal assistant behavior",
        ],
        success_metrics=[
            "Time to first useful artifact",
            "PR acceptance rate",
            "Regression rate",
            "Reviewer minutes saved",
        ],
        assumptions=[
            "A repository or project context can be provided",
            "Users prefer approval gates for high-risk actions",
        ],
        unknowns=[
            "Primary buyer segment and pricing model",
            "Hosted vs self-hosted adoption split",
        ],
    )


def build_prfaq(brief: ProductBrief) -> PRFAQDocument:
    headline = f"{brief.title} Launches AI-Operated Software Delivery Workflows"
    press_release_summary = (
        f"{brief.title} helps teams move from idea to release with coordinated "
        "specialist agents, structured planning artifacts, and measurable quality gates."
    )

    customer_faq = [
        FAQItem(
            question="Who is this product for?",
            answer=", ".join(brief.target_users),
        ),
        FAQItem(
            question="What outcome can I expect?",
            answer="A roadmap, implementation plan, review artifacts, and release readiness report.",
        ),
        FAQItem(
            question="How is risk controlled?",
            answer="High-risk actions require explicit approval and produce audit-friendly artifacts.",
        ),
    ]

    internal_faq = [
        FAQItem(
            question="What differentiates this from coding-only agents?",
            answer="It handles idea-to-release workflows, not only code generation.",
        ),
        FAQItem(
            question="What is the smallest useful launch scope?",
            answer="GitHub-first workflows with product brief, stack decision, roadmap, PR summary, and release checks.",
        ),
    ]

    launch_criteria = [
        "Core company workflow models are available via CLI",
        "Each workflow emits structured JSON artifacts",
        "Release readiness checks are available for local repositories",
    ]

    return PRFAQDocument(
        headline=headline,
        press_release_summary=press_release_summary,
        customer_faq=customer_faq,
        internal_faq=internal_faq,
        launch_criteria=launch_criteria,
    )


def recommend_tech_stack(
    repo_path: str | Path,
    *,
    product_focus: str = "AI software delivery workflow",
) -> TechStackDecision:
    resolved = Path(repo_path).resolve()
    signals = _detect_repo_signals(resolved)
    detected = sorted(name for name, present in signals.items() if present)

    constraints = [
        "Preserve current repository strengths and contributor familiarity",
        "Prefer standards that support packaging, testing, and MCP integration",
        "Minimize operational complexity in early product phases",
    ]

    option_python = TechOptionScore(
        option_name="Python engine + optional web layer later",
        scores={
            "delivery_speed": 5,
            "maintainability": 4,
            "ecosystem_fit": 5 if signals["python"] else 3,
            "operational_simplicity": 4,
            "team_familiarity": 4,
        },
        total_score=0,
        notes="Strong fit with existing codebase and packaging flow.",
    )
    option_hybrid = TechOptionScore(
        option_name="Python engine + TypeScript UI and API gateway",
        scores={
            "delivery_speed": 4,
            "maintainability": 4,
            "ecosystem_fit": 5 if signals["node"] else 4,
            "operational_simplicity": 3,
            "team_familiarity": 4,
        },
        total_score=0,
        notes="Best route to no-code product surface while preserving the engine.",
    )
    option_rewrite = TechOptionScore(
        option_name="Full TypeScript rewrite",
        scores={
            "delivery_speed": 2,
            "maintainability": 3,
            "ecosystem_fit": 3,
            "operational_simplicity": 2,
            "team_familiarity": 3,
        },
        total_score=0,
        notes="High migration risk with limited near-term upside.",
    )

    options = [option_python, option_hybrid, option_rewrite]
    for option in options:
        option.total_score = sum(option.scores.values())

    recommended = max(options, key=lambda item: item.total_score)
    rationale = (
        f"For {product_focus}, the recommended path is '{recommended.option_name}' "
        "because it maximizes near-term delivery while keeping release quality predictable."
    )

    risks = [
        "Introducing a UI/API layer adds operational responsibilities",
        "Dual-language stack requires explicit ownership boundaries",
    ]
    if not signals["python"]:
        risks.append("Repository does not currently signal a Python-first stack.")

    return TechStackDecision(
        context=f"Repository analysis for {resolved}",
        constraints=constraints,
        options=options,
        recommended_option=recommended.option_name,
        rationale=rationale,
        risks=risks,
        detected_signals=detected,
    )


def build_architecture_rfc(
    brief: ProductBrief,
    stack: TechStackDecision,
) -> ArchitectureRFC:
    rfc_id = f"rfc-{_slugify(brief.title)}"
    decision = (
        "Keep the parallel-agents engine as the execution core and add "
        "a company-workflow orchestration layer with explicit approval gates."
    )
    alternatives = [
        "CLI-only evolution without workflow artifacts",
        "Full rewrite as a new platform before validating workflow value",
    ]
    tradeoffs = [
        "Faster delivery by reusing engine code vs slower UI-first rewrite",
        "More complexity from gateway/session layer vs better no-code usability",
    ]
    security = [
        "Default permission profile should remain read-focused",
        "Write actions must require approval in public/team contexts",
    ]
    rollout = [
        "Phase 1: Company workflow models and CLI commands",
        "Phase 2: GitHub-first issue and PR workflows",
        "Phase 3: Gateway/job system",
        "Phase 4: Local desktop office and hosted MCP surface",
    ]
    return ArchitectureRFC(
        id=rfc_id,
        title=f"{brief.title} Architecture RFC",
        context=brief.problem_statement,
        decision=f"{decision} Recommended stack path: {stack.recommended_option}.",
        alternatives=alternatives,
        tradeoffs=tradeoffs,
        security_considerations=security,
        rollout_plan=rollout,
    )


def build_roadmap(brief: ProductBrief, horizon_weeks: int = 12) -> RoadmapPlan:
    weeks = max(1, horizon_weeks)
    items = [
        RoadmapItem(
            id="RM-01",
            title="Define product and workflow artifacts",
            owner_role="Product Agent",
            milestone="M1",
            acceptance_criteria=[
                "Product brief, PR/FAQ, and quality bar exist",
                "Tech stack policy and operating model are documented",
            ],
        ),
        RoadmapItem(
            id="RM-02",
            title="Implement company workflow models and CLI surface",
            owner_role="Architecture Agent",
            milestone="M1",
            acceptance_criteria=[
                "Structured models exist in code",
                "CLI can generate brief, stack decision, roadmap, and release checks",
            ],
            dependencies=["RM-01"],
        ),
        RoadmapItem(
            id="RM-03",
            title="Integrate GitHub-first planning and PR workflows",
            owner_role="Planning Agent",
            milestone="M2",
            acceptance_criteria=[
                "Roadmap items can map to issues",
                "PR-ready summaries and risk reports can be generated",
            ],
            dependencies=["RM-02"],
        ),
        RoadmapItem(
            id="RM-04",
            title="Add release readiness policy enforcement",
            owner_role="Release Agent",
            milestone="M2",
            acceptance_criteria=[
                "Release readiness checks return machine-readable status",
                "Blocking issues are surfaced consistently",
            ],
            dependencies=["RM-02"],
        ),
    ]
    outcomes = [
        f"Deliver a repeatable idea-to-release workflow in {weeks} weeks",
        "Increase confidence in AI-generated delivery artifacts",
        "Enable no-code product surface without engine rewrite",
    ]
    return RoadmapPlan(
        name=f"{brief.title} Roadmap",
        horizon_weeks=weeks,
        outcomes=outcomes,
        items=items,
    )


def build_sprint_plan(
    roadmap: RoadmapPlan,
    *,
    milestone: str,
    horizon_days: int = 14,
) -> SprintPlan:
    milestone_name = _normalize_text(milestone)
    if not milestone_name:
        raise ValueError("Milestone cannot be empty.")
    if horizon_days <= 0:
        raise ValueError("horizon_days must be greater than 0.")

    selected = [
        item for item in roadmap.items
        if item.milestone.strip().lower() == milestone_name.lower()
    ]
    if not selected:
        raise ValueError(f"No roadmap items found for milestone '{milestone_name}'.")

    items = [
        SprintPlanItem(
            source_item_id=item.id,
            title=item.title,
            owner_role=item.owner_role,
            acceptance_criteria=item.acceptance_criteria,
            dependencies=item.dependencies,
        )
        for item in selected
    ]
    dependency_risks = [
        f"{item.id} depends on {', '.join(item.dependencies)}"
        for item in selected
        if item.dependencies
    ]
    risks = dependency_risks or ["No explicit roadmap dependencies for this sprint."]
    goals = [
        f"Complete milestone {milestone_name} scope from {roadmap.name}",
        *roadmap.outcomes[:2],
    ]

    return SprintPlan(
        name=f"{roadmap.name} {milestone_name} Sprint",
        milestone=milestone_name,
        horizon_days=horizon_days,
        goals=goals,
        items=items,
        risks=risks,
    )


def build_issue_plan_from_roadmap(
    roadmap: RoadmapPlan,
    *,
    default_labels: list[str] | None = None,
) -> list[PlannedIssue]:
    labels = default_labels or ["planning", "ai-agents"]
    planned: list[PlannedIssue] = []
    for item in roadmap.items:
        acceptance = item.acceptance_criteria or ["Define acceptance criteria."]
        dependencies = item.dependencies or ["None"]
        body_lines = [
            "## Context",
            f"Generated from roadmap `{roadmap.name}`.",
            "",
            "## Owner Role",
            item.owner_role,
            "",
            "## Acceptance Criteria",
            *[f"- {criterion}" for criterion in acceptance],
            "",
            "## Dependencies",
            *[f"- {dependency}" for dependency in dependencies],
        ]
        planned.append(
            PlannedIssue(
                source_item_id=item.id,
                title=f"[{item.id}] {item.title}",
                body="\n".join(body_lines),
                milestone=item.milestone,
                labels=labels,
            )
        )
    return planned


def build_github_workflow_templates(roadmap: RoadmapPlan | None = None) -> dict[str, Any]:
    labels = [
        {
            "name": "planning",
            "color": "0e8a16",
            "description": "Project planning and roadmap work",
        },
        {
            "name": "ai-agents",
            "color": "5319e7",
            "description": "Work involving agent orchestration or AI workflow behavior",
        },
        {
            "name": "release-readiness",
            "color": "fbca04",
            "description": "Release checks, packaging, and launch readiness",
        },
        {
            "name": "needs-approval",
            "color": "d93f0b",
            "description": "Human approval is required before write actions continue",
        },
    ]
    milestone_names: list[str]
    if roadmap:
        milestone_names = sorted({item.milestone for item in roadmap.items if item.milestone})
    else:
        milestone_names = ["M1", "M2"]

    return {
        "labels": labels,
        "milestones": [
            {
                "title": name,
                "description": f"Parallel Agents Office delivery milestone {name}",
            }
            for name in milestone_names
        ],
        "branch_policy": {
            "prefix": "pa",
            "format": "pa/<source-item-id>-<slug>",
            "max_length": 80,
        },
    }


def build_branch_name(issue: str, title: str, *, prefix: str = "pa", max_length: int = 80) -> str:
    clean_prefix = _slugify(prefix)
    clean_issue = _slugify(issue)
    clean_title = _slugify(title)
    branch = f"{clean_prefix}/{clean_issue}-{clean_title}" if clean_title else f"{clean_prefix}/{clean_issue}"
    if len(branch) <= max_length:
        return branch
    prefix_part = f"{clean_prefix}/{clean_issue}-"
    remaining = max(1, max_length - len(prefix_part))
    return f"{prefix_part}{clean_title[:remaining].strip('-')}"


def render_pr_summary(
    final_output: Mapping[str, Any],
    *,
    run_id: str | None = None,
    artifacts: Mapping[str, str] | None = None,
) -> str:
    summary = str(final_output.get("summary") or "No summary provided.")
    risk_report = final_output.get("risk_report") or []
    metadata = final_output.get("metadata") or {}
    tests_run = metadata.get("tests_run") or metadata.get("tests") or []
    if isinstance(tests_run, str):
        tests = [tests_run]
    elif isinstance(tests_run, list):
        tests = [str(item) for item in tests_run]
    else:
        tests = []

    lines = ["# Pull Request Summary", ""]
    if run_id:
        lines.extend([f"- Run ID: `{run_id}`", ""])
    lines.extend(["## Summary", "", summary, ""])
    lines.extend(["## Risk Report", ""])
    if risk_report:
        for item in risk_report:
            if isinstance(item, Mapping):
                severity = item.get("severity", "unknown")
                title = item.get("title", "Untitled risk")
                lines.append(f"- [{severity}] {title}")
            else:
                lines.append(f"- {item}")
    else:
        lines.append("- No risk items reported.")
    lines.extend(["", "## Tests", ""])
    if tests:
        lines.extend(f"- {test}" for test in tests)
    else:
        lines.append("- Not reported.")
    lines.extend(["", "## Artifacts", ""])
    if artifacts:
        lines.extend(f"- `{name}`: {path}" for name, path in sorted(artifacts.items()))
    else:
        lines.append("- No run-linked artifacts found.")
    lines.append("")
    return "\n".join(lines)


def build_release_readiness_report(repo_path: str | Path) -> ReleaseReadinessReport:
    resolved = Path(repo_path).resolve()
    items = [
        _check_exists(
            resolved / "README.md",
            name="README",
            fail_if_missing=True,
            missing_details="README.md is missing.",
            pass_details="README.md present.",
        ),
        _check_exists(
            resolved / "CHANGELOG.md",
            name="Changelog",
            fail_if_missing=True,
            missing_details="CHANGELOG.md is missing.",
            pass_details="CHANGELOG.md present.",
        ),
        _check_packaging(resolved),
        _check_tests(resolved),
        _check_ci(resolved),
        _check_exists(
            resolved / "SECURITY.md",
            name="Security Policy",
            fail_if_missing=False,
            missing_details="SECURITY.md is missing.",
            pass_details="SECURITY.md present.",
        ),
    ]

    blocking = [item.details for item in items if item.status == "fail"]
    status: Literal["ready", "needs_attention", "blocked"]
    if blocking:
        status = "blocked"
    elif any(item.status == "warn" for item in items):
        status = "needs_attention"
    else:
        status = "ready"

    next_actions = [item.details for item in items if item.status in {"fail", "warn"}]
    if not next_actions:
        next_actions = ["All tracked release checks passed."]

    return ReleaseReadinessReport(
        repo_path=str(resolved),
        status=status,
        items=items,
        blocking_issues=blocking,
        next_actions=next_actions,
    )


def build_post_release_review(
    *,
    release_id: str,
    release_report: ReleaseReadinessReport,
    metrics: dict[str, Any] | None = None,
) -> PostReleaseReview:
    clean_release_id = _normalize_text(release_id)
    if not clean_release_id:
        raise ValueError("release_id cannot be empty.")

    outcomes = [
        f"{item.name}: {item.status} - {item.details}"
        for item in release_report.items
    ]
    incidents = release_report.blocking_issues.copy()
    if not incidents and release_report.status == "ready":
        incidents = ["No blocking release incidents reported."]

    priority: Literal["low", "medium", "high"] = "high" if release_report.status == "blocked" else "medium"
    follow_ups = [
        PostReleaseFollowUp(
            title=action,
            owner_role="Release Agent",
            priority=priority,
            source="release-check",
        )
        for action in release_report.next_actions
        if action != "All tracked release checks passed."
    ]

    summary = (
        f"Release {clean_release_id} finished with readiness status "
        f"'{release_report.status}' for {release_report.repo_path}."
    )
    return PostReleaseReview(
        release_id=clean_release_id,
        summary=summary,
        outcomes=outcomes,
        incidents=incidents,
        metrics=metrics or {},
        follow_up_items=follow_ups,
    )


def _check_exists(
    path: Path,
    *,
    name: str,
    fail_if_missing: bool,
    missing_details: str,
    pass_details: str,
) -> ReleaseCheckItem:
    if path.exists():
        return ReleaseCheckItem(name=name, status="pass", details=pass_details)
    status: Literal["warn", "fail"] = "fail" if fail_if_missing else "warn"
    return ReleaseCheckItem(name=name, status=status, details=missing_details)


def _check_packaging(repo: Path) -> ReleaseCheckItem:
    has_pyproject = (repo / "pyproject.toml").exists()
    has_package_json = (repo / "package.json").exists() or (repo / "npm-wrapper" / "package.json").exists()
    if has_pyproject or has_package_json:
        return ReleaseCheckItem(
            name="Packaging Metadata",
            status="pass",
            details="Packaging metadata detected.",
        )
    return ReleaseCheckItem(
        name="Packaging Metadata",
        status="fail",
        details="No pyproject.toml or package.json detected.",
    )


def _check_tests(repo: Path) -> ReleaseCheckItem:
    tests_dir = repo / "tests"
    if tests_dir.exists() and any(tests_dir.glob("test_*.py")):
        return ReleaseCheckItem(
            name="Tests",
            status="pass",
            details="Test directory and test files detected.",
        )
    if tests_dir.exists():
        return ReleaseCheckItem(
            name="Tests",
            status="warn",
            details="tests/ exists but test_*.py files were not found.",
        )
    return ReleaseCheckItem(
        name="Tests",
        status="fail",
        details="tests/ directory is missing.",
    )


def _check_ci(repo: Path) -> ReleaseCheckItem:
    workflow_dir = repo / ".github" / "workflows"
    if workflow_dir.exists() and any(workflow_dir.glob("*.yml")):
        return ReleaseCheckItem(
            name="CI Workflows",
            status="pass",
            details="GitHub workflow file detected.",
        )
    if workflow_dir.exists() and any(workflow_dir.glob("*.yaml")):
        return ReleaseCheckItem(
            name="CI Workflows",
            status="pass",
            details="GitHub workflow file detected.",
        )
    return ReleaseCheckItem(
        name="CI Workflows",
        status="warn",
        details="No GitHub workflow files detected in .github/workflows.",
    )


def _detect_repo_signals(repo: Path) -> dict[str, bool]:
    return {
        "python": (repo / "pyproject.toml").exists() or (repo / "requirements.txt").exists(),
        "node": (repo / "package.json").exists() or (repo / "npm-wrapper" / "package.json").exists(),
        "typescript": (repo / "tsconfig.json").exists(),
        "go": (repo / "go.mod").exists(),
        "rust": (repo / "Cargo.toml").exists(),
    }
