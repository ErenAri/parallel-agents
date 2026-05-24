from __future__ import annotations

from parallel_agents.company_policy import (
    CompanyApplyPolicy,
    derive_policy_from_issue_plan,
    validate_issue_plan_against_policy,
)


def test_derive_policy_from_issue_plan_collects_repo_labels_milestones():
    issue_plan = [
        {"title": "A", "labels": ["planning", "ai-agents"], "milestone": "M1"},
        {"title": "B", "labels": ["planning"], "milestone": "M2"},
    ]
    policy = derive_policy_from_issue_plan("owner/repo", issue_plan)

    assert policy.repo_allowlist == ["owner/repo"]
    assert policy.label_allowlist == ["ai-agents", "planning"]
    assert policy.milestone_allowlist == ["M1", "M2"]


def test_validate_issue_plan_against_policy_blocks_repo_labels_and_milestones():
    issue_plan = [
        {"title": "A", "labels": ["planning", "restricted"], "milestone": "M2"},
    ]
    policy = CompanyApplyPolicy(
        repo_allowlist=["owner/repo"],
        label_allowlist=["planning"],
        milestone_allowlist=["M1"],
    )

    violations = validate_issue_plan_against_policy(
        repo_ref="other/repo",
        issue_plan=issue_plan,
        policy=policy,
    )

    assert len(violations) >= 3
    assert any("not in repo_allowlist" in item for item in violations)
    assert any("disallowed label" in item for item in violations)
    assert any("disallowed milestone" in item for item in violations)


def test_validate_issue_plan_against_policy_enforces_patterns():
    issue_plan = [
        {"title": "A", "labels": ["bad,label"], "milestone": "M1%"},
    ]
    policy = CompanyApplyPolicy(
        label_pattern=r"^[a-z-]+$",
        milestone_pattern=r"^M[0-9]+$",
    )

    violations = validate_issue_plan_against_policy(
        repo_ref="owner/repo",
        issue_plan=issue_plan,
        policy=policy,
    )

    assert any("violates label_pattern" in item for item in violations)
    assert any("violates milestone_pattern" in item for item in violations)
