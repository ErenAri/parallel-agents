from __future__ import annotations

from parallel_agents.company_workflows import (
    ReleaseReadinessReport,
    build_branch_name,
    build_github_workflow_templates,
    build_issue_plan_from_roadmap,
    build_post_release_review,
    build_release_readiness_report,
    build_roadmap,
    build_sprint_plan,
    create_product_brief,
    issue_plan_items,
    recommend_tech_stack,
    render_pr_summary,
)


def test_issue_plan_items_prefers_normalized_then_falls_back():
    # network artifact: normalized list under issue_plan is preferred
    network = {"issue_plan": [{"title": "a"}], "issues": [{"title": "tracking-only"}]}
    assert issue_plan_items(network) == [{"title": "a"}]

    # desktop artifact: only the issues key (full dump) is used as fallback
    desktop = {"issues": [{"title": "b", "body": "x"}]}
    assert issue_plan_items(desktop) == [{"title": "b", "body": "x"}]

    # empty / malformed shapes degrade to an empty list
    assert issue_plan_items({}) == []
    assert issue_plan_items({"issue_plan": None, "issues": "nope"}) == []


def test_create_product_brief_normalizes_input():
    brief = create_product_brief("  build   a   no-code   release assistant  ")
    assert brief.title == "Build A No-Code Release Assistant"
    assert brief.problem_statement == "build a no-code release assistant"
    assert brief.id.startswith("brief-")
    assert brief.goals
    assert brief.success_metrics


def test_recommend_tech_stack_detects_python_and_node(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    npm_wrapper = tmp_path / "npm-wrapper"
    npm_wrapper.mkdir()
    (npm_wrapper / "package.json").write_text('{"name":"demo"}', encoding="utf-8")

    decision = recommend_tech_stack(tmp_path)

    assert "python" in decision.detected_signals
    assert "node" in decision.detected_signals
    assert decision.options
    assert decision.recommended_option


def test_build_roadmap_clamps_horizon():
    brief = create_product_brief("Build planning automation")
    roadmap = build_roadmap(brief, horizon_weeks=0)
    assert roadmap.horizon_weeks == 1
    assert roadmap.items


def test_release_readiness_report_blocked_without_required_files(tmp_path):
    report = build_release_readiness_report(tmp_path)
    assert report.status == "blocked"
    assert report.blocking_issues


def test_build_issue_plan_from_roadmap_generates_items():
    brief = create_product_brief("Build planning automation")
    roadmap = build_roadmap(brief, horizon_weeks=8)
    issues = build_issue_plan_from_roadmap(roadmap, default_labels=["planning"])
    assert len(issues) == len(roadmap.items)
    assert issues[0].title.startswith("[")
    assert "Acceptance Criteria" in issues[0].body


def test_build_sprint_plan_filters_by_milestone():
    brief = create_product_brief("Build planning automation")
    roadmap = build_roadmap(brief, horizon_weeks=8)
    sprint = build_sprint_plan(roadmap, milestone="M1", horizon_days=10)

    assert sprint.milestone == "M1"
    assert sprint.horizon_days == 10
    assert sprint.items
    assert all(item.status == "planned" for item in sprint.items)
    assert all(item.source_item_id.startswith("RM-") for item in sprint.items)


def test_build_sprint_plan_rejects_missing_milestone():
    brief = create_product_brief("Build planning automation")
    roadmap = build_roadmap(brief, horizon_weeks=8)

    try:
        build_sprint_plan(roadmap, milestone="M99")
    except ValueError as exc:
        assert "No roadmap items" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_build_post_release_review_from_release_check(tmp_path):
    report = ReleaseReadinessReport(
        repo_path=str(tmp_path),
        status="blocked",
        blocking_issues=["README.md is missing."],
        next_actions=["Add README.md"],
    )

    review = build_post_release_review(
        release_id="v1",
        release_report=report,
        metrics={"downloads": 12},
    )

    assert review.release_id == "v1"
    assert review.metrics["downloads"] == 12
    assert review.incidents == ["README.md is missing."]
    assert review.follow_up_items[0].priority == "high"


def test_github_templates_branch_name_and_pr_summary():
    brief = create_product_brief("Build planning automation")
    roadmap = build_roadmap(brief, horizon_weeks=8)
    templates = build_github_workflow_templates(roadmap)
    branch = build_branch_name("RM-01", "Define Product And Workflow Artifacts")
    summary = render_pr_summary(
        {
            "summary": "Implemented workflow artifacts.",
            "risk_report": [{"severity": "low", "title": "No migration risk"}],
            "metadata": {"tests_run": ["pytest -q"]},
        },
        run_id="run-1",
        artifacts={"brief": "/tmp/brief.json"},
    )

    assert templates["labels"]
    assert templates["milestones"]
    assert branch == "pa/rm-01-define-product-and-workflow-artifacts"
    assert "Implemented workflow artifacts." in summary
    assert "pytest -q" in summary
